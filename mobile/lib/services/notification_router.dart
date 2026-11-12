/// Small indirection so services can hand a notification payload to the app
/// without importing `main.dart`. If navigation is not ready yet (cold start,
/// login screen), the payload is kept until [flush] is called.
class NotificationRouter {
  NotificationRouter._();

  static bool Function(String payload)? handler;
  static String? _pending;

  static void receive(String payload) {
    if (payload.isEmpty) return;
    if (handler?.call(payload) == true) return;
    _pending = payload;
  }

  static void flush() {
    final payload = _pending;
    if (payload == null) return;
    _pending = null;
    handler?.call(payload);
  }
}
