import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_service.dart';
import 'ws_channel_stub.dart'
    if (dart.library.io) 'ws_channel_io.dart';

enum RealtimeVoiceState { idle, connecting, ready, live, failed, closed }

class RealtimeTurn {
  RealtimeTurn({
    required this.user,
    required this.assistant,
    this.interrupted = false,
  });

  final String user;
  final String assistant;
  final bool interrupted;
}

/// Full-duplex MOSS-Live conversation over the xzrobot gateway.
///
/// Protocol (via the gateway's transparent proxy):
///   attach_session → session_attached → session.update → session.updated
///   → media.mode(tagged-v1) + mic_state(enabled)
///   → uplink 0x00 + 16kHz PCM16 20ms frames (continuously, silence included)
///   ← response.audio.context + raw 48kHz PCM16 (1:1)
///   → playback.chunk.completed / playback.completed / playback.stopped
///
/// Barge-in is decided by the model: on response.audio.stop the client stops
/// immediately and reports played_audio_ms, then waits for response.interrupted.
class RealtimeVoiceController extends ChangeNotifier {
  static const int _upRate = 16000;
  static const int _downRate = 48000;
  static const int _frameBytes = _upRate * 2 * 20 ~/ 1000; // 640
  static const MethodChannel _player = MethodChannel('omniaide/voice_audio');

  RealtimeVoiceState state = RealtimeVoiceState.idle;
  String status = '点击开始，和 MOSS 实时对话';
  String? errorText;
  String userText = '';
  String assistantText = '';
  bool micOn = false;
  bool speaking = false;
  final List<RealtimeTurn> turns = [];

  final AudioRecorder _recorder = AudioRecorder();
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _wsSub;
  StreamSubscription<Uint8List>? _micSub;
  final BytesBuilder _micBuf = BytesBuilder(copy: true);
  Timer? _attachTimer;
  Timer? _ackTimer;

  final Map<String, _Run> _runs = {};
  final List<_AudioItem> _audioItems = [];
  Map<String, dynamic>? _pendingContext;
  DateTime? _playbackStartAt;
  int _playbackCursorMs = 0;
  bool _closing = false;
  bool _archived = false;
  bool _disposed = false;

  bool get active =>
      state == RealtimeVoiceState.connecting ||
      state == RealtimeVoiceState.ready ||
      state == RealtimeVoiceState.live;

  Future<void> connect() async {
    if (active) return;
    _closing = false;
    errorText = null;
    userText = '';
    assistantText = '';
    turns.clear();
    _setState(RealtimeVoiceState.connecting, '正在连接 MOSS-Live…');

    try {
      final cfg = await _fetchConfig();
      final base = Uri.parse(cfg['url'] as String);
      final uri = base.replace(queryParameters: {
        ...base.queryParameters,
        'model': (cfg['model'] ?? 'moss-live-1.0').toString(),
        'user': (cfg['user'] ?? '').toString(),
      });

      final channel = connectVoiceSocket(uri, (cfg['token'] ?? '').toString());
      _channel = channel;
      await channel.ready.timeout(const Duration(seconds: 10));

      _wsSub = channel.stream.listen(
        _onWsMessage,
        onError: (Object e) => _fail('连接出错：$e'),
        onDone: () {
          if (!_closing) _fail('MOSS 连接已断开');
        },
      );
      _sendJson({'action': 'attach_session'});
      _attachTimer = Timer(const Duration(seconds: 10), () {
        if (state == RealtimeVoiceState.connecting) {
          _fail('连接超时：MOSS 没有回应');
        }
      });
    } catch (e) {
      _fail('连接失败：${_short(e)}');
    }
  }

  Future<void> close() async {
    _closing = true;
    _attachTimer?.cancel();
    _attachTimer = null;
    _ackTimer?.cancel();
    _micSub?.cancel();
    _micSub = null;
    _micBuf.clear();
    try {
      await _recorder.stop();
    } catch (_) {}
    micOn = false;
    await _stopPlayback();
    try {
      await _channel?.sink.close(1000, 'client_end');
    } catch (_) {}
    _channel = null;
    _wsSub?.cancel();
    _wsSub = null;
    _sendSpeaker(false);
    _setState(RealtimeVoiceState.idle, '已结束，点击重新开始');
  }

  Future<Map<String, dynamic>> _fetchConfig() async {
    final api = ApiService();
    final token = api.token;
    if (token == null || token.isEmpty) throw Exception('请先登录');
    final res = await http.get(
      Uri.parse('${api.baseUrl}/api/chat/voice/moss'),
      headers: {'Authorization': 'Bearer $token'},
    ).timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) {
      throw Exception(_detail(res.body, res.statusCode));
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  // ---------------- websocket ----------------

  void _onWsMessage(dynamic message) {
    if (message is String) {
      _onText(message);
    } else if (message is Uint8List) {
      _onBinary(message);
    } else if (message is List<int>) {
      _onBinary(Uint8List.fromList(message));
    }
  }

  void _onText(String raw) {
    Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    final action = (msg['action'] ?? '').toString();
    final data = (msg['data'] as Map?)?.cast<String, dynamic>() ?? const {};

    switch (action) {
      case 'session_attached':
        _attachTimer?.cancel();
        _attachTimer = null;
        _setState(RealtimeVoiceState.ready, '正在准备会话…');
        _sendJson({
          'action': 'session.update',
          'session': {
            'persona': {
              'name': '小安',
              'prompt': '你是 OmniAide 的语音助手，语气自然、简洁，像是在打电话。',
            },
            'instructions': '用简体中文口语化回答，尽量简短，不要使用 Markdown。',
          },
        });
        break;
      case 'session.updated':
        final error = (data['error'] ?? '').toString();
        if (error.isNotEmpty) {
          _fail('会话配置失败：$error');
          return;
        }
        _sendJson({'action': 'media.mode', 'binary_protocol': 'tagged-v1'});
        _sendJson({'action': 'mic_state', 'enabled': true});
        unawaited(_startMic());
        _setState(RealtimeVoiceState.live, '正在聆听，直接说话');
        break;
      case 'input.speech.started':
        speaking = false;
        _archived = false;
        _status('正在聆听…');
        break;
      case 'input.speech.stopped':
        _status('正在思考…');
        break;
      case 'input.transcript.updated':
      case 'input.transcript.done':
        userText = (data['text'] ?? userText).toString();
        _notify();
        break;
      case 'output.transcript.updated':
      case 'output.transcript.done':
        assistantText = (data['text'] ?? assistantText).toString();
        _notify();
        break;
      case 'response.audio.started':
        speaking = true;
        _status('正在回答，直接说话就能打断');
        break;
      case 'response.audio.context':
        _pendingContext = data;
        _registerContext(data);
        break;
      case 'response.audio.done':
        _onAudioDone(data);
        break;
      case 'response.audio.stop':
        _onAudioStop(data);
        break;
      case 'response.interrupted':
        speaking = false;
        _archiveTurn(interrupted: true);
        _status('已打断，请继续说');
        break;
      case 'response.ended':
        speaking = false;
        _archiveTurn();
        if (state == RealtimeVoiceState.live) {
          _setState(RealtimeVoiceState.live, '正在聆听，直接说话');
        }
        break;
      case 'error':
        final err = (data['error'] as Map?)?.cast<String, dynamic>() ?? const {};
        final local = data['local'] == true;
        errorText = (err['message'] ?? '上游返回错误').toString();
        if (!local) {
          _fail(errorText!);
        } else {
          _notify();
        }
        break;
      default:
        break;
    }
  }

  void _sendJson(Map<String, dynamic> payload) {
    final channel = _channel;
    if (channel == null) return;
    try {
      channel.sink.add(jsonEncode(payload));
    } catch (_) {}
  }

  // ---------------- microphone ----------------

  Future<void> _startMic() async {
    if (micOn) return;
    try {
      if (!await _recorder.hasPermission()) {
        errorText = '需要麦克风权限';
        _notify();
        return;
      }
      await _configureAudioSession();
      final stream = await _recorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: _upRate,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
        streamBufferSize: _frameBytes * 4,
        androidConfig: AndroidRecordConfig(
          audioSource: AndroidAudioSource.voiceCommunication,
          audioManagerMode: AudioManagerMode.modeInCommunication,
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
      micOn = true;
      _micSub = stream.listen(_onMicData, onError: (Object e) {
        errorText = '麦克风读取失败：$e';
        _notify();
      });
      _sendSpeaker(true);
      _notify();
    } catch (e) {
      errorText = '麦克风启动失败：${_short(e)}';
      _notify();
    }
  }

  void _onMicData(Uint8List chunk) {
    if (chunk.isEmpty) return;
    if (state != RealtimeVoiceState.ready &&
        state != RealtimeVoiceState.live) {
      return;
    }
    _micBuf.add(chunk);
    final bytes = _micBuf.takeBytes();
    var offset = 0;
    while (bytes.length - offset >= _frameBytes) {
      final frame = Uint8List(1 + _frameBytes);
      frame[0] = 0x00; // tagged-v1: audio
      frame.setRange(1, 1 + _frameBytes, bytes, offset);
      _channel?.sink.add(frame);
      offset += _frameBytes;
    }
    if (offset < bytes.length) {
      _micBuf.add(Uint8List.sublistView(bytes, offset));
    }
  }

  Future<void> _configureAudioSession() async {
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

  void _sendSpeaker(bool on) {
    if (defaultTargetPlatform != TargetPlatform.iOS) return;
    try {
      _player.invokeMethod(on ? 'speakerOn' : 'speakerOff');
    } catch (_) {}
  }

  // ---------------- audio playback ----------------

  Future<void> _onBinary(Uint8List pcm) async {
    final context = _pendingContext;
    _pendingContext = null;
    if (pcm.isEmpty) return;

    if (_playbackStartAt == null) {
      _playbackStartAt = DateTime.now().add(const Duration(milliseconds: 100));
      _playbackCursorMs = 0;
      _audioItems.clear();
      _ackTimer?.cancel();
      _ackTimer = Timer.periodic(
        const Duration(milliseconds: 30),
        (_) => _tickAcks(),
      );
      if (defaultTargetPlatform == TargetPlatform.iOS) {
        try {
          await _player.invokeMethod(
            'playbackStart',
            {'sampleRate': _downRate},
          );
        } catch (_) {}
      }
    }

    final durationMs = pcm.length / 2 / (_downRate / 1000);
    final item = _AudioItem(
      runId: context?['run_id']?.toString() ?? '',
      turnId: context?['turn_id']?.toString() ?? '',
      chunkId: context?['chunk_id']?.toString() ?? '',
      durationMs: durationMs,
      startMs: _playbackCursorMs,
    );
    _playbackCursorMs += durationMs.round();
    _audioItems.add(item);

    if (defaultTargetPlatform == TargetPlatform.iOS) {
      try {
        await _player.invokeMethod('playbackPush', pcm);
      } catch (e) {
        errorText = '播放失败：${_short(e)}';
        _notify();
      }
    }
  }

  void _registerContext(Map<String, dynamic> data) {
    final runId = data['run_id']?.toString() ?? '';
    final run = _runs.putIfAbsent(runId, () => _Run());
    run.turnId = data['turn_id']?.toString() ?? run.turnId;
    final chunkId = data['chunk_id']?.toString() ?? '';
    if (chunkId.isNotEmpty) run.pending.add(chunkId);
  }

  void _tickAcks() {
    final start = _playbackStartAt;
    if (start == null) return;
    final now = DateTime.now();
    for (final item in List<_AudioItem>.of(_audioItems)) {
      if (item.acked) continue;
      final end = start.add(Duration(
        milliseconds: item.startMs + item.durationMs.round(),
      ));
      if (!now.isAfter(end)) continue;
      item.acked = true;
      _sendJson({
        'action': 'playback.chunk.completed',
        'chunk_id': item.chunkId,
        'run_id': item.runId,
        'turn_id': item.turnId,
      });
      final run = _runs[item.runId];
      if (run != null) {
        run.pending.remove(item.chunkId);
        if (run.audioDone && run.pending.isEmpty) {
          _completeRun(item.runId, run);
        }
      }
    }
    _audioItems.removeWhere((item) => item.acked);
  }

  void _onAudioDone(Map<String, dynamic> data) {
    final runId = data['run_id']?.toString() ?? '';
    final run = _runs[runId];
    if (run == null) return;
    run.audioDone = true;
    if (run.pending.isEmpty) _completeRun(runId, run);
  }

  void _completeRun(String runId, _Run run) {
    if (run.completed) return;
    run.completed = true;
    _sendJson({
      'action': 'playback.completed',
      'run_id': runId,
      'turn_id': run.turnId,
    });
    _runs.remove(runId);
  }

  void _onAudioStop(Map<String, dynamic> data) {
    final start = _playbackStartAt;
    var playedMs = 0;
    _AudioItem? current;
    if (start != null) {
      final elapsed = DateTime.now().difference(start).inMilliseconds;
      for (final item in _audioItems) {
        if (item.acked) continue;
        if (elapsed < item.startMs) break;
        final end = item.startMs + item.durationMs.round();
        if (elapsed < end) {
          current = item;
          playedMs = elapsed - item.startMs;
          break;
        }
        current = item;
        playedMs = item.durationMs.round();
      }
    }
    _sendJson({
      'action': 'playback.stopped',
      'run_id': data['run_id']?.toString() ?? current?.runId,
      'turn_id': data['turn_id']?.toString() ?? current?.turnId,
      'played_audio_ms': playedMs.clamp(0, 1 << 30),
    });
    if (current != null) _runs.remove(current.runId);
    unawaited(_stopPlayback());
    speaking = false;
    _status('已打断，请继续说');
  }

  Future<void> _stopPlayback() async {
    _ackTimer?.cancel();
    _ackTimer = null;
    _audioItems.clear();
    _pendingContext = null;
    _playbackStartAt = null;
    _playbackCursorMs = 0;
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      try {
        await _player.invokeMethod('playbackStop');
      } catch (_) {}
    }
  }

  // ---------------- state ----------------

  void _archiveTurn({bool interrupted = false}) {
    if (_archived) return;
    if (userText.isEmpty && assistantText.isEmpty) return;
    turns.add(RealtimeTurn(
      user: userText,
      assistant: assistantText,
      interrupted: interrupted,
    ));
    _archived = true;
    userText = '';
    assistantText = '';
    _notify();
  }

  void _status(String text) {
    status = text;
    _notify();
  }

  void _setState(RealtimeVoiceState next, String text) {
    state = next;
    status = text;
    if (next == RealtimeVoiceState.ready || next == RealtimeVoiceState.live) {
      _archived = false;
    }
    _notify();
  }

  void _fail(String message) {
    errorText = message;
    _closing = true;
    _attachTimer?.cancel();
    _attachTimer = null;
    _ackTimer?.cancel();
    _ackTimer = null;
    _stopPlayback();
    _micSub?.cancel();
    _micSub = null;
    unawaited(() async {
      try {
        await _recorder.stop();
      } catch (_) {}
    }());
    micOn = false;
    try {
      _channel?.sink.close(4000, 'failed');
    } catch (_) {}
    _channel = null;
    _setState(RealtimeVoiceState.failed, message);
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  static String _short(Object e) =>
      e.toString().replaceFirst('Exception: ', '').replaceFirst('SocketException: ', '');

  static String _detail(String body, int status) {
    try {
      final data = jsonDecode(body);
      if (data is Map && data['detail'] != null) return data['detail'].toString();
    } catch (_) {}
    return body.isEmpty ? '请求失败（$status）' : body;
  }

  @override
  void dispose() {
    _disposed = true;
    _micSub?.cancel();
    _wsSub?.cancel();
    _attachTimer?.cancel();
    _ackTimer?.cancel();
    _recorder.dispose();
    super.dispose();
  }
}

class _AudioItem {
  _AudioItem({
    required this.runId,
    required this.turnId,
    required this.chunkId,
    required this.durationMs,
    required this.startMs,
  });

  final String runId;
  final String turnId;
  final String chunkId;
  final double durationMs;
  final int startMs;
  bool acked = false;
}

class _Run {
  String turnId = '';
  bool audioDone = false;
  bool completed = false;
  final Set<String> pending = {};
}
