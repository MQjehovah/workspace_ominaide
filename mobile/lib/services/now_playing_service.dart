import 'package:flutter/services.dart';

/// Bridges the music player state to iOS lock-screen / Control Center and
/// forwards remote commands back to the Flutter player.
class NowPlayingService {
  static const _channel = MethodChannel('omniaide/media');
  static final NowPlayingService _instance = NowPlayingService._();
  factory NowPlayingService() => _instance;
  NowPlayingService._();

  /// Called with command names: play, pause, toggle, next, previous, seek.
  /// [position] is only set for seek (seconds).
  void Function(String command, double? position)? onCommand;

  bool _initialized = false;

  void init() {
    if (_initialized) return;
    _initialized = true;
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'play':
          onCommand?.call('play', null);
        case 'pause':
          onCommand?.call('pause', null);
        case 'toggle':
          onCommand?.call('toggle', null);
        case 'next':
          onCommand?.call('next', null);
        case 'previous':
          onCommand?.call('previous', null);
        case 'seek':
          final args = call.arguments is Map ? call.arguments as Map : null;
          onCommand?.call(
            'seek',
            (args?['position'] as num?)?.toDouble(),
          );
      }
      return null;
    });
  }

  Future<void> update({
    required String title,
    required Duration duration,
    required Duration position,
    required bool playing,
  }) async {
    try {
      await _channel.invokeMethod('update', <String, dynamic>{
        'title': title,
        'artist': 'OmniAide',
        'duration': duration.inMilliseconds / 1000.0,
        'position': position.inMilliseconds / 1000.0,
        'playing': playing,
      });
    } catch (_) {
      // Android/web have no native media channel yet.
    }
  }

  Future<void> clear() async {
    try {
      await _channel.invokeMethod('clear');
    } catch (_) {}
  }
}
