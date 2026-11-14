import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:just_audio/just_audio.dart';
import 'package:record/record.dart';

import 'api_service.dart';

enum VoicePhase { idle, listening, recording, thinking, speaking, error }

class VoiceTurn {
  VoiceTurn({this.transcript = '', this.reply = ''});

  String transcript;
  String reply;
  bool interrupted = false;
  bool done = false;
}

/// Continuous, barge-in capable voice conversation.
///
/// Keeps one microphone stream open for the whole session and runs a small
/// energy VAD on 20ms frames:
///   * silence → speech        starts an utterance (with 600ms pre-roll)
///   * speech → 700ms silence  ends it and sends the WAV to the backend
///   * while the assistant speaks, sustained speech above a higher threshold
///     stops playback immediately and starts a new utterance
///
/// The backend streams NDJSON: transcript / delta / audio(sentence PCM) / done.
class VoiceSessionController extends ChangeNotifier {
  static const int sampleRate = 16000;
  static const int _frameMs = 20;
  static const int _frameBytes = sampleRate * 2 * _frameMs ~/ 1000;

  final AudioRecorder _recorder = AudioRecorder();
  // just_audio plays from an in-memory byte stream (audioplayers' iOS plugin
  // does not implement setSourceBytes). The player must not touch the audio
  // session: record keeps it in playAndRecord + voice-processing mode so the
  // microphone can stay open while the answer is playing.
  final AudioPlayer _player = AudioPlayer(
    handleInterruptions: false,
    handleAudioSessionActivation: false,
    androidApplyAudioAttributes: false,
  );

  VoicePhase phase = VoicePhase.idle;
  String status = '点击开始，然后直接说话';
  String? errorText;
  final List<VoiceTurn> turns = [];
  double level = 0;
  bool autoInterrupt = true;
  bool micActive = false;

  String? _sessionId;
  VoiceTurn? _active;

  StreamSubscription<Uint8List>? _micSub;
  StreamSubscription<PlayerState>? _playerSub;
  StreamSubscription<String>? _lineSub;
  http.Client? _client;
  final BytesBuilder _pending = BytesBuilder(copy: true);
  final List<_SpeechFrame> _utterance = [];
  final List<_SpeechFrame> _preRoll = [];
  int _preRollBytes = 0;
  int _firstVoice = -1;
  int _lastVoice = -1;
  final List<Uint8List> _audioQueue = [];
  int _turnId = 0;
  int _lastAudioAt = 0;
  // Echo probe: mute the answer for a moment and check whether the "speech"
  // survives. Speaker leakage disappears instantly; a real voice does not.
  bool _probing = false;
  int _probeStartAt = 0;
  int _probeConfirmMs = 0;
  double _probeLevel = 0;
  double _echoGate = 0;
  int _probeCooldownUntil = 0;

  bool _capturing = false;
  bool _playing = false;
  bool _streamDone = false;
  bool _starting = false;
  bool _disposed = false;
  int _speechMs = 0;
  int _silenceMs = 0;
  int _bargeMs = 0;
  int _utteranceMs = 0;
  int _lastLevelNotify = 0;

  double _noiseFloor = 120;

  bool get busy =>
      phase == VoicePhase.recording ||
      phase == VoicePhase.thinking ||
      phase == VoicePhase.speaking;

  Future<void> start() async {
    if (_starting ||
        phase == VoicePhase.listening ||
        phase == VoicePhase.recording ||
        phase == VoicePhase.thinking ||
        phase == VoicePhase.speaking) {
      return;
    }
    _starting = true;
    try {
      if (!await _recorder.hasPermission()) {
        _fail('需要麦克风权限才能语音对话');
        return;
      }
      await _resetPlayback();
      await _configureVoiceSession();
      _sessionId ??= 'mobile-voice-${DateTime.now().millisecondsSinceEpoch}';
      final stream = await _recorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: sampleRate,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
        streamBufferSize: _frameBytes * 4,
        androidConfig: AndroidRecordConfig(
          audioSource: AndroidAudioSource.voiceCommunication,
          audioManagerMode: AudioManagerMode.modeInCommunication,
          // Forcing the speaker keeps the AEC reference aligned with the
          // actual acoustic path instead of silently switching routes.
          speakerphone: true,
          manageBluetooth: true,
        ),
        iosConfig: IosRecordConfig(
          categoryOptions: [
            IosAudioCategoryOption.defaultToSpeaker,
            IosAudioCategoryOption.allowBluetooth,
          ],
        ),
      ));
      micActive = true;
      await _setSpeaker(true);
      _micSub = stream.listen(
        _onAudio,
        onError: (Object e) => _fail('录音失败：$e'),
      );
      _playerSub ??= _player.playerStateStream.listen(_onPlayerState);
      _setPhase(VoicePhase.listening, '正在聆听，请直接说话');
    } catch (e) {
      _fail('麦克风启动失败：$e');
    } finally {
      _starting = false;
    }
  }

  Future<void> stop() async {
    _capturing = false;
    _streamDone = false;
    _speechMs = 0;
    _silenceMs = 0;
    _bargeMs = 0;
    _utterance.clear();
    _preRoll.clear();
    _preRollBytes = 0;
    _firstVoice = -1;
    _lastVoice = -1;
    _turnId += 1;
    _abortStream();
    await _resetPlayback();
    await _micSub?.cancel();
    _micSub = null;
    try {
      await _recorder.stop();
    } catch (_) {}
    micActive = false;
    _sessionId = null;
    level = 0;
    await _setSpeaker(false);
    _setPhase(VoicePhase.idle, '已结束，点击重新开始');
  }

  void setAutoInterrupt(bool value) {
    autoInterrupt = value;
    _notify();
  }

  // ---------------- microphone / VAD ----------------

  void _onAudio(Uint8List chunk) {
    if (chunk.isEmpty) return;
    _pending.add(chunk);
    final bytes = _pending.takeBytes();
    var offset = 0;
    while (bytes.length - offset >= _frameBytes) {
      final frame = Uint8List.sublistView(bytes, offset, offset + _frameBytes);
      offset += _frameBytes;
      _processFrame(frame);
    }
    if (offset < bytes.length) {
      _pending.add(Uint8List.sublistView(bytes, offset));
    }
  }

  void _processFrame(Uint8List frame) {
    final rms = _rms(frame);
    level = (rms / 3200).clamp(0.0, 1.0);

    final threshold = math.max(320.0, _noiseFloor * 2.8);
    final speech = rms > threshold;
    _pushPreRoll(_SpeechFrame(frame, speech));
    if (!speech) {
      _noiseFloor = _noiseFloor * 0.95 + rms * 0.05;
    }

    if (_capturing) {
      final index = _utterance.length;
      _utterance.add(_SpeechFrame(frame, speech));
      _utteranceMs += _frameMs;
      if (speech) {
        _lastVoice = index;
        if (_firstVoice < 0) _firstVoice = index;
      }
      _silenceMs = speech ? 0 : _silenceMs + _frameMs;
      if (_silenceMs >= 700 || _utteranceMs >= 30000) {
        _finishUtterance();
      }
    } else if (phase == VoicePhase.thinking) {
      if (autoInterrupt) {
        // The user can change their mind while the answer is being prepared:
        // speaking now drops the pending turn and starts a new one.
        final barge = math.max(1000.0, _noiseFloor * 5);
        _bargeMs = rms > barge ? _bargeMs + _frameMs : 0;
        if (_bargeMs >= 200) _bargeIn();
      }
    } else if (phase == VoicePhase.speaking) {
      if (autoInterrupt) {
        final now = DateTime.now().millisecondsSinceEpoch;
        if (_probing) {
          // Give the speaker ~90ms to go silent, then require the sound to
          // continue for 140ms with the answer muted.
          final elapsed = now - _probeStartAt;
          if (elapsed > 90) {
            final confirm = math.max(600.0, _noiseFloor * 3.5);
            if (rms > confirm) {
              _probeConfirmMs += _frameMs;
            } else {
              _probeConfirmMs = 0;
            }
            if (_probeConfirmMs >= 140) {
              _bargeIn();
              return;
            }
          }
          if (elapsed > 320) {
            // It was our own audio: remember this echo level so it does not
            // trigger another probe on the next sentence.
            _probing = false;
            _probeConfirmMs = 0;
            _bargeMs = 0;
            _echoGate = math.max(_echoGate, _probeLevel);
            _probeCooldownUntil = now + 400;
            try {
              _player.setVolume(1.0);
            } catch (_) {}
          }
        } else {
          final sinceAudio = now - _lastAudioAt;
          final threshold = math.max(
            950.0,
            math.max(_noiseFloor * 6, _echoGate * 1.2),
          );
          if (now > _probeCooldownUntil &&
              sinceAudio > 350 &&
              rms > threshold) {
            _bargeMs += _frameMs;
            if (_bargeMs >= 100) {
              _probing = true;
              _probeStartAt = now;
              _probeConfirmMs = 0;
              _probeLevel = rms;
              _bargeMs = 0;
              try {
                _player.setVolume(0.0);
              } catch (_) {}
            }
          } else {
            _bargeMs = 0;
          }
        }
      }
    } else if (phase == VoicePhase.listening) {
      _speechMs = speech
          ? _speechMs + _frameMs
          : math.max(0, _speechMs - _frameMs * 2);
      if (_speechMs >= 60) _beginUtterance();
    }

    _notifyLevel();
  }

  void _beginUtterance({bool fromBarge = false}) {
    _capturing = true;
    _speechMs = 0;
    _silenceMs = 0;
    _bargeMs = 0;
    _utteranceMs = 0;
    _utterance.clear();
    _utterance.addAll(_preRoll);
    _utteranceMs = _utterance.length * _frameMs;
    _firstVoice = -1;
    _lastVoice = -1;
    for (var i = 0; i < _utterance.length; i++) {
      if (_utterance[i].speech) {
        if (_firstVoice < 0) _firstVoice = i;
        _lastVoice = i;
      }
    }
    _preRoll.clear();
    _preRollBytes = 0;
    errorText = null;
    _setPhase(
      VoicePhase.recording,
      fromBarge ? '已打断，继续说吧' : '正在听你说…',
    );
  }

  void _pushPreRoll(_SpeechFrame frame) {
    // Keep ~600ms so the first syllable is never lost when we start capturing.
    _preRoll.add(frame);
    _preRollBytes += frame.bytes.length;
    const limit = sampleRate * 2 * 600 ~/ 1000;
    while (_preRollBytes > limit && _preRoll.isNotEmpty) {
      _preRollBytes -= _preRoll.removeAt(0).bytes.length;
    }
  }

  Future<void> _finishUtterance() async {
    if (!_capturing) return;
    _capturing = false;
    // Keep 200ms around the detected speech and drop leading/trailing silence:
    // ASR latency scales with clip length, and the VAD already waited 700ms.
    final start = _firstVoice < 0 ? 0 : math.max(0, _firstVoice - 10);
    final end = _lastVoice < 0
        ? _utterance.length - 1
        : math.min(_utterance.length - 1, _lastVoice + 10);
    final bytes = BytesBuilder(copy: false);
    if (_utterance.isNotEmpty && end >= start) {
      for (var i = start; i <= end; i++) {
        bytes.add(_utterance[i].bytes);
      }
    }
    final pcm = bytes.takeBytes();
    _utterance.clear();
    // Ignore clicks and very short noises.
    if (pcm.length < sampleRate * 2 * 250 ~/ 1000) {
      _setPhase(VoicePhase.listening, '没听清，再说一次');
      return;
    }
    final turn = VoiceTurn();
    turns.add(turn);
    _active = turn;
    _setPhase(VoicePhase.thinking, '正在识别…');
    await _sendTurn(pcm, turn);
  }

  // ---------------- backend stream ----------------

  Future<void> _sendTurn(Uint8List pcm, VoiceTurn turn) async {
    final int turnId = ++_turnId;
    _abortStream();
    // Start every turn from an empty player. Reusing the previous turn's
    // playlist left just_audio parked at the end, so only the first answer
    // ever played.
    await _resetPlayback();
    _streamDone = false;
    final api = ApiService();
    final token = api.token;
    if (token == null || token.isEmpty) {
      _fail('请先登录');
      return;
    }
    final sessionId = _sessionId;
    if (sessionId == null) return;

    final client = http.Client();
    _client = client;
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('${api.baseUrl}/api/chat/voice/stream'),
      );
      request.headers['Authorization'] = 'Bearer $token';
      request.fields['session_id'] = sessionId;
      request.files.add(http.MultipartFile.fromBytes(
        'file',
        _wav(pcm),
        filename: 'turn.wav',
        contentType: MediaType('audio', 'wav'),
      ));
      final response = await client.send(request);
      if (turnId != _turnId) {
        // The user interrupted before the response headers arrived.
        client.close();
        return;
      }
      if (response.statusCode != 200) {
        final body = await response.stream.bytesToString();
        throw Exception(_errorText(body, response.statusCode));
      }
      _lineSub = response.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(
        (line) {
          if (turnId != _turnId) return;
          _handleLine(line, turn);
        },
        onError: (Object e) {
          if (turnId != _turnId) return;
          if (phase != VoicePhase.recording) {
            _fail('语音连接中断：$e');
          }
        },
        onDone: () {
          if (turnId != _turnId) return;
          _streamDone = true;
          if (phase == VoicePhase.speaking || phase == VoicePhase.thinking) {
            if (!_playing && _audioQueue.isEmpty) _completeTurn();
          }
        },
        cancelOnError: true,
      );
    } catch (e) {
      if (_client == client && phase != VoicePhase.recording) {
        final message = e.toString().replaceFirst('Exception: ', '');
        errorText = message;
        if (micActive) {
          // Keep the session alive: a bad ASR result should not end the call.
          _setPhase(VoicePhase.listening, '没听清：$message');
        } else {
          _fail(message);
        }
      }
    }
  }

  void _handleLine(String line, VoiceTurn turn) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) return;
    Map<String, dynamic> msg;
    try {
      msg = jsonDecode(trimmed) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    switch (msg['t']) {
      case 'transcript':
        turn.transcript = (msg['text'] ?? '').toString();
        _notify();
        break;
      case 'status':
        status = (msg['text'] ?? '').toString();
        _notify();
        break;
      case 'delta':
        turn.reply += (msg['text'] ?? '').toString();
        _notify();
        break;
      case 'audio':
        final pcm = base64Decode((msg['pcm'] ?? '').toString());
        final rate = (msg['rate'] as num?)?.toInt() ?? 24000;
        _enqueueAudio(_wav(pcm, rate));
        break;
      case 'done':
        turn.done = true;
        turn.interrupted = msg['interrupted'] == true;
        _streamDone = true;
        if (!_playing && _audioQueue.isEmpty) _completeTurn();
        break;
    }
  }

  // ---------------- playback ----------------

  void _enqueueAudio(Uint8List wav) {
    _lastAudioAt = DateTime.now().millisecondsSinceEpoch;
    if (phase != VoicePhase.speaking) {
      _setPhase(VoicePhase.speaking, '正在回答，可直接打断');
    }
    _audioQueue.add(wav);
    if (!_playing) unawaited(_playNext());
  }

  /// Play one sentence at a time. A playlist that finishes before the next
  /// sentence is ready leaves just_audio parked at the end on iOS, so the
  /// remaining sentences were never played; a plain FIFO avoids that.
  Future<void> _playNext() async {
    if (_playing) return;
    if (_audioQueue.isEmpty) {
      if (_streamDone) _completeTurn();
      return;
    }
    final wav = _audioQueue.removeAt(0);
    _playing = true;
    try {
      await _player.setAudioSource(_WavSource(wav));
      await _player.play();
      _lastAudioAt = DateTime.now().millisecondsSinceEpoch;
    } catch (e) {
      _playing = false;
      errorText = '语音播放失败：${e.toString().replaceFirst('Exception: ', '')}';
      _notify();
      unawaited(_playNext());
    }
  }

  void _onPlayerState(PlayerState state) {
    if (state.processingState != ProcessingState.completed) return;
    _playing = false;
    unawaited(_playNext());
  }

  /// Configure the shared audio session as a voice call, not media playback.
  ///
  /// AEC needs the render reference: iOS only runs VoiceProcessingIO in
  /// ``playAndRecord`` + ``voiceChat`` mode, and Android only inserts the
  /// hardware echo canceller for ``voice_communication``. Without this the
  /// mic hears the TTS untouched and the agent interrupts itself.
  Future<void> _configureVoiceSession() async {
    final session = await AudioSession.instance;
    await session.configure(AudioSessionConfiguration(
      avAudioSessionCategory: AVAudioSessionCategory.playAndRecord,
      avAudioSessionCategoryOptions:
          AVAudioSessionCategoryOptions.defaultToSpeaker |
              AVAudioSessionCategoryOptions.allowBluetooth,
      avAudioSessionMode: AVAudioSessionMode.voiceChat,
      androidAudioAttributes: const AndroidAudioAttributes(
        contentType: AndroidAudioContentType.speech,
        usage: AndroidAudioUsage.voiceCommunication,
      ),
      androidAudioFocusGainType: AndroidAudioFocusGainType.gainTransient,
      androidWillPauseWhenDucked: false,
    ));
    await session.setActive(true);
  }

  /// .voiceChat biases output to the earpiece; keep the mode but force the
  /// speaker so AEC stays available.
  Future<void> _setSpeaker(bool on) async {
    if (defaultTargetPlatform != TargetPlatform.iOS) return;
    try {
      await const MethodChannel('omniaide/voice_audio')
          .invokeMethod(on ? 'speakerOn' : 'speakerOff');
    } catch (_) {}
  }

  Future<void> _resetPlayback() async {
    _audioQueue.clear();
    _probing = false;
    _probeConfirmMs = 0;
    _bargeMs = 0;
    _echoGate = 0;
    _probeCooldownUntil = 0;
    _playing = false;
    try {
      await _player.setVolume(1.0);
    } catch (_) {}
    try {
      await _player.stop();
    } catch (_) {}
    try {
      await _player.clearAudioSources();
    } catch (_) {}
  }

  void _completeTurn() {
    if (phase == VoicePhase.listening) return;
    _streamDone = false;
    _playing = false;
    _audioQueue.clear();
    _active?.done = true;
    _setPhase(VoicePhase.listening, '继续说话，或点击结束');
  }

  void _bargeIn() {
    // Invalidate the running turn first: any buffered deltas/audio that arrive
    // after the interruption must not push the UI back into thinking/speaking.
    _turnId += 1;
    _bargeMs = 0;
    _streamDone = false;
    unawaited(_resetPlayback());
    final turn = _active;
    if (turn != null && !turn.done) {
      turn.interrupted = true;
    }
    // Switch to recording before closing the HTTP stream so the resulting
    // onError/onDone callbacks do not tear the session down.
    if (micActive) {
      _beginUtterance(fromBarge: true);
    } else {
      _setPhase(VoicePhase.idle, '已打断');
    }
    _abortStream();
    _abortServerTurn();
    _notify();
  }

  void _abortStream() {
    _lineSub?.cancel();
    _lineSub = null;
    _client?.close();
    _client = null;
  }

  void _abortServerTurn() {
    final sessionId = _sessionId;
    final api = ApiService();
    final token = api.token;
    if (sessionId == null || token == null || token.isEmpty) return;
    unawaited(() async {
      try {
        await http
            .post(
              Uri.parse('${api.baseUrl}/api/chat/voice/interrupt'),
              headers: {
                'Authorization': 'Bearer $token',
                'Content-Type': 'application/json',
              },
              body: jsonEncode({'session_id': sessionId}),
            )
            .timeout(const Duration(seconds: 3));
      } catch (_) {}
    }());
  }

  // ---------------- helpers ----------------

  void _fail(String message) {
    _capturing = false;
    _streamDone = false;
    _abortStream();
    errorText = message;
    if (micActive) unawaited(_hardStopMic());
    _setPhase(VoicePhase.error, message);
  }

  Future<void> _hardStopMic() async {
    await _micSub?.cancel();
    _micSub = null;
    try {
      await _recorder.stop();
    } catch (_) {}
    micActive = false;
  }

  void _setPhase(VoicePhase next, String message) {
    phase = next;
    status = message;
    if (!_disposed) notifyListeners();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  void _notifyLevel() {
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _lastLevelNotify < 80) return;
    _lastLevelNotify = now;
    if (!_disposed) notifyListeners();
  }

  static double _rms(Uint8List bytes) {
    if (bytes.length < 2) return 0;
    final data = ByteData.sublistView(bytes);
    var sum = 0.0;
    var count = 0;
    for (var i = 0; i + 1 < bytes.length; i += 2) {
      final value = data.getInt16(i, Endian.little);
      sum += value * value;
      count++;
    }
    return count == 0 ? 0 : math.sqrt(sum / count);
  }

  static Uint8List _wav(Uint8List pcm, [int rate = sampleRate]) {
    final header = ByteData(44);
    void ascii(int offset, String value) {
      for (var i = 0; i < value.length; i++) {
        header.setUint8(offset + i, value.codeUnitAt(i));
      }
    }

    ascii(0, 'RIFF');
    header.setUint32(4, 36 + pcm.length, Endian.little);
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    header.setUint32(16, 16, Endian.little);
    header.setUint16(20, 1, Endian.little);
    header.setUint16(22, 1, Endian.little);
    header.setUint32(24, rate, Endian.little);
    header.setUint32(28, rate * 2, Endian.little);
    header.setUint16(32, 2, Endian.little);
    header.setUint16(34, 16, Endian.little);
    ascii(36, 'data');
    header.setUint32(40, pcm.length, Endian.little);

    final out = BytesBuilder(copy: false)
      ..add(header.buffer.asUint8List())
      ..add(pcm);
    return out.takeBytes();
  }

  static String _errorText(String body, int status) {
    try {
      final data = jsonDecode(body);
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
    } catch (_) {}
    return body.isEmpty ? '语音请求失败（$status）' : body;
  }

  @override
  void dispose() {
    _disposed = true;
    _micSub?.cancel();
    _lineSub?.cancel();
    _client?.close();
    unawaited(() async {
      try {
        await _recorder.stop();
      } catch (_) {}
      try {
        await _player.stop();
      } catch (_) {}
    }());
    _recorder.dispose();
    _player.dispose();
    super.dispose();
  }
}


class _SpeechFrame {
  const _SpeechFrame(this.bytes, this.speech);

  final Uint8List bytes;
  final bool speech;
}


class _WavSource extends StreamAudioSource {
  _WavSource(this._bytes);

  final Uint8List _bytes;

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    var from = start ?? 0;
    var to = end ?? _bytes.length;
    if (from < 0) from = 0;
    if (to > _bytes.length) to = _bytes.length;
    if (to < from) to = from;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: to - from,
      offset: from,
      stream: Stream.value(_bytes.sublist(from, to)),
      contentType: 'audio/wav',
    );
  }
}
