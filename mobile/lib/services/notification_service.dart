import 'dart:async';

import 'host_channel_service.dart';

/// Listens to notification pushes on the shared host channel
/// (`channel: "notifications"`) and surfaces them to the UI via a callback.
class NotificationService {
  StreamSubscription<Map<String, dynamic>>? _sub;

  static final NotificationService _instance = NotificationService._();
  factory NotificationService() => _instance;
  NotificationService._();

  /// Start listening. [onNotification] is called with title/body when a new
  /// notification arrives.
  Future<void> start(Function(String title, String body) onNotification) async {
    await _sub?.cancel();
    final host = HostChannelService();
    await host.ensureConnected();
    _sub = host.stream.listen((msg) {
      if (msg['channel'] != 'notifications') return;
      final title = (msg['title'] as String?) ?? '新通知';
      final body = (msg['body'] as String?) ?? '';
      onNotification(title, body);
    });
  }

  void stop() {
    _sub?.cancel();
    _sub = null;
    HostChannelService().stop();
  }
}
