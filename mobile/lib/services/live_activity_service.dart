import 'package:flutter/services.dart';

/// Thin bridge to the iOS Live Activity widget extension.
///
/// Live Activities surface the current coding run on the Lock Screen and in
/// the Dynamic Island while the app is in the background. iOS is the only
/// platform that can draw something system-wide; calls are no-ops elsewhere.
class LiveActivityService {
  static const MethodChannel _channel = MethodChannel('omniaide/live_activity');

  String? _signature;

  Future<void> sync({
    required String title,
    required int count,
    required DateTime startedAt,
    String status = 'running',
    String action = '',
  }) async {
    final signature =
        '$title|$count|${startedAt.millisecondsSinceEpoch}|$status|$action';
    if (_signature == signature) return;
    _signature = signature;
    try {
      await _channel.invokeMethod('sync', {
        'title': title,
        'count': count,
        'startedAt': startedAt.millisecondsSinceEpoch,
        'status': status,
        'action': action,
      });
    } on MissingPluginException {
      // Android/desktop, or an iOS build without the widget extension.
    } catch (_) {
      // Live Activities disabled by the user: the in-app bubble still works.
    }
  }

  Future<void> end({
    required String title,
    required int count,
    required DateTime startedAt,
    required String status,
    required String duration,
  }) async {
    _signature = null;
    try {
      await _channel.invokeMethod('end', {
        'title': title,
        'count': count,
        'startedAt': startedAt.millisecondsSinceEpoch,
        'status': status,
        'duration': duration,
      });
    } on MissingPluginException {
      // Ignore on non-iOS platforms.
    } catch (_) {}
  }

  Future<void> endAll() async {
    _signature = null;
    try {
      await _channel.invokeMethod('endAll');
    } on MissingPluginException {
      // Ignore on non-iOS platforms.
    } catch (_) {}
  }
}
