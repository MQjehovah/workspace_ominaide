import 'dart:async';

import 'host_channel_service.dart';

/// Listens to notification pushes on the shared host channel
/// (`channel: "notifications"`) and surfaces them to the UI via a callback.
class NotificationService {
  StreamSubscription<Map<String, dynamic>>? _sub;
  bool _stopped = false;

  static final NotificationService _instance = NotificationService._();
  factory NotificationService() => _instance;
  NotificationService._();

  /// Start listening. [onNotification] is called with title/body when a new
  /// notification arrives.
  Future<void> start(Function(String title, String body) onNotification) async {
    _stopped = false;
    await _sub?.cancel();
    final host = HostChannelService();
    await host.ensureConnected();
    if (_stopped) return;
    _sub = host.stream.listen((msg) {
      if (msg['channel'] != 'notifications') return;
      final title = (msg['title'] as String?) ?? '新通知';
      final body = (msg['body'] as String?) ?? '';
      onNotification(title, body);
    });
  }

  /// Stop listening for notification pushes.
  ///
  /// The underlying [HostChannelService] connection is shared by every realtime
  /// consumer (notifications, vibecoding, local tools). Tearing it down here
  /// used to drop the vibecoding session stream whenever the home screen was
  /// rebuilt, which showed up as "离线" in the remote session screen.
  void stop() {
    _stopped = true;
    _sub?.cancel();
    _sub = null;
  }
}
