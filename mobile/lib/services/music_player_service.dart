import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_service.dart';
import 'music_cache.dart';
import 'now_playing_service.dart';

enum MusicPlayMode { sequential, repeatAll, repeatOne, shuffle }

/// App-wide music player.
///
/// Playback lives here instead of inside [MusicScreen] so navigating away keeps
/// the music running. The mini player and the full screen both listen to this
/// notifier.
class MusicPlayerService extends ChangeNotifier {
  static final MusicPlayerService _instance = MusicPlayerService._();
  factory MusicPlayerService() => _instance;
  MusicPlayerService._();

  final AudioPlayer _player = AudioPlayer();

  List<Map<String, dynamic>> _queue = [];
  int? _index;
  MusicPlayMode _mode = MusicPlayMode.sequential;
  List<int> _shuffleOrder = [];
  int _shufflePos = -1;
  bool _playing = false;
  bool _buffering = false;
  bool _initialized = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  List<Map<String, dynamic>> get queue => List.unmodifiable(_queue);
  int? get index => _index;
  bool get playing => _playing;
  bool get buffering => _buffering;
  Duration get position => _position;
  Duration get duration => _duration;
  MusicPlayMode get mode => _mode;

  Map<String, dynamic>? get current {
    final at = _index;
    if (at == null || at < 0 || at >= _queue.length) return null;
    return _queue[at];
  }

  String get modeLabel {
    switch (_mode) {
      case MusicPlayMode.sequential:
        return '顺序播放';
      case MusicPlayMode.repeatAll:
        return '列表循环';
      case MusicPlayMode.repeatOne:
        return '单曲循环';
      case MusicPlayMode.shuffle:
        return '随机播放';
    }
  }

  bool isCurrent(Map<String, dynamic> song) {
    final now = current;
    if (now == null) return false;
    return now['file_id'] != null && now['file_id'] == song['file_id'];
  }

  void initialize() {
    if (_initialized) return;
    _initialized = true;
    _loadMode();
    NowPlayingService().init();
    NowPlayingService().onCommand = _onRemoteCommand;
    _player.onPositionChanged.listen((value) {
      _position = value;
      notifyListeners();
    });
    _player.onDurationChanged.listen((value) {
      _duration = value;
      _updateNowPlaying();
      notifyListeners();
    });
    _player.onPlayerComplete.listen((_) => _handleComplete());
  }

  Future<void> _loadMode() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString('music.playMode');
      final mode = MusicPlayMode.values.firstWhere(
        (value) => value.name == saved,
        orElse: () => MusicPlayMode.sequential,
      );
      _mode = mode;
      notifyListeners();
    } catch (_) {
      // Preferences are optional.
    }
  }

  Future<void> _saveMode() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('music.playMode', _mode.name);
    } catch (_) {
      // Ignore.
    }
  }

  void cycleMode() {
    _mode =
        MusicPlayMode.values[(_mode.index + 1) % MusicPlayMode.values.length];
    if (_mode == MusicPlayMode.shuffle) {
      _resetShuffle(start: _index);
    }
    _saveMode();
    notifyListeners();
  }

  void _resetShuffle({int? start}) {
    if (_queue.isEmpty) {
      _shuffleOrder = [];
      _shufflePos = -1;
      return;
    }
    _shuffleOrder = List<int>.generate(_queue.length, (i) => i)..shuffle();
    if (start != null && start >= 0 && start < _queue.length) {
      _shuffleOrder.remove(start);
      _shuffleOrder.insert(0, start);
      _shufflePos = 0;
    } else {
      _shufflePos = -1;
    }
  }

  int _nextShuffleIndex() {
    if (_queue.isEmpty) return 0;
    if (_shuffleOrder.length != _queue.length) {
      _resetShuffle(start: _index);
    }
    _shufflePos++;
    if (_shufflePos >= _shuffleOrder.length) {
      _resetShuffle();
      _shufflePos = 0;
    }
    return _shuffleOrder[_shufflePos];
  }

  int _prevShuffleIndex() {
    if (_queue.isEmpty) return 0;
    if (_shuffleOrder.length != _queue.length) {
      _resetShuffle(start: _index);
    }
    _shufflePos = _shufflePos <= 0 ? _shuffleOrder.length - 1 : _shufflePos - 1;
    return _shuffleOrder[_shufflePos];
  }

  Future<void> playQueue(
    List<Map<String, dynamic>> songs,
    int startIndex,
  ) async {
    initialize();
    if (songs.isEmpty) return;
    _queue = List<Map<String, dynamic>>.from(songs);
    final start = startIndex.clamp(0, _queue.length - 1);
    _index = start;
    _resetShuffle(start: _mode == MusicPlayMode.shuffle ? start : null);
    await _playIndex(start);
  }

  Future<void> toggle() async {
    if (current == null) return;
    try {
      if (_playing) {
        await _player.pause();
        _playing = false;
      } else {
        await _player.resume();
        _playing = true;
      }
    } catch (_) {
      return;
    }
    _updateNowPlaying();
    notifyListeners();
  }

  Future<void> seek(Duration target) async {
    await _player.seek(target);
    _position = target;
    _updateNowPlaying();
    notifyListeners();
  }

  Future<void> next() async {
    if (_queue.isEmpty) return;
    if (_mode == MusicPlayMode.shuffle) {
      await _playIndex(_nextShuffleIndex());
      return;
    }
    final at = _index ?? 0;
    if (at + 1 < _queue.length) {
      await _playIndex(at + 1);
    } else if (_mode == MusicPlayMode.repeatAll) {
      await _playIndex(0);
    }
  }

  Future<void> previous() async {
    if (_queue.isEmpty) return;
    if (_mode == MusicPlayMode.shuffle) {
      await _playIndex(_prevShuffleIndex());
      return;
    }
    final at = _index ?? 0;
    if (at > 0) {
      await _playIndex(at - 1);
    } else if (_mode == MusicPlayMode.repeatAll) {
      await _playIndex(_queue.length - 1);
    }
  }

  Future<void> _handleComplete() async {
    final at = _index;
    if (at == null) return;
    switch (_mode) {
      case MusicPlayMode.repeatOne:
        try {
          await _player.seek(Duration.zero);
          await _player.resume();
          _playing = true;
          _position = Duration.zero;
          _updateNowPlaying();
          notifyListeners();
        } catch (_) {
          await _playIndex(at);
        }
        break;
      case MusicPlayMode.repeatAll:
        await _playIndex(at + 1 >= _queue.length ? 0 : at + 1);
        break;
      case MusicPlayMode.shuffle:
        await _playIndex(_nextShuffleIndex());
        break;
      case MusicPlayMode.sequential:
        if (at + 1 < _queue.length) {
          await _playIndex(at + 1);
        } else {
          _playing = false;
          _position = Duration.zero;
          _updateNowPlaying();
          notifyListeners();
        }
        break;
    }
  }

  Future<void> _playIndex(int index) async {
    if (index < 0 || index >= _queue.length) return;
    await _player.stop();
    final song = _queue[index];
    _index = index;
    _playing = false;
    _buffering = true;
    _position = Duration.zero;
    _duration = Duration.zero;
    notifyListeners();
    try {
      final fileId = (song['file_id'] as num).toInt();
      final name = (song['name'] ?? 'track.mp3').toString();
      final cached = await MusicCache().cachedTrack(fileId, name);
      if (cached != null) {
        await _player.play(DeviceFileSource(cached.path));
      } else {
        // Stream immediately through the Range-aware endpoint, then fill the
        // cache in the background so the next play is instant and offline.
        final uri = await ApiService().fileStreamUri(fileId);
        try {
          await _player.play(UrlSource(uri.toString()));
        } catch (_) {
          final file = await MusicCache().cacheTrack(fileId, name);
          await _player.play(DeviceFileSource(file.path));
        }
        unawaited(() async {
          try {
            await MusicCache().cacheTrack(fileId, name);
          } catch (_) {}
        }());
      }
      _playing = true;
      _updateNowPlaying();
    } catch (error) {
      _playing = false;
      _buffering = false;
      notifyListeners();
      rethrow;
    } finally {
      _buffering = false;
      notifyListeners();
    }
  }

  Future<void> stop() async {
    try {
      await _player.stop();
    } catch (_) {}
    _playing = false;
    _position = Duration.zero;
    _updateNowPlaying();
    notifyListeners();
  }

  void _updateNowPlaying() {
    final song = current;
    if (song == null) return;
    NowPlayingService().update(
      title: (song['name'] ?? '音乐').toString(),
      duration: _duration,
      position: _position,
      playing: _playing,
    );
  }

  Future<void> _onRemoteCommand(String command, double? position) async {
    switch (command) {
      case 'play':
        if (!_playing) await toggle();
        break;
      case 'pause':
        if (_playing) await toggle();
        break;
      case 'toggle':
        await toggle();
        break;
      case 'next':
        await next();
        break;
      case 'previous':
        await previous();
        break;
      case 'seek':
        if (position != null) {
          await seek(Duration(milliseconds: (position * 1000).round()));
        }
        break;
    }
  }
}
