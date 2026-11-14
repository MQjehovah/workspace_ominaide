import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// Native WebSocket with the gateway key in the handshake header. The
/// gateway rejects query-string auth for this key, so the header is required.
WebSocketChannel connectVoiceSocket(Uri uri, String token) {
  return IOWebSocketChannel.connect(
    uri,
    headers: {'Authorization': 'Bearer $token'},
    pingInterval: const Duration(seconds: 20),
  );
}
