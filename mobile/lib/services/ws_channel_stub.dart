import 'package:web_socket_channel/web_socket_channel.dart';

/// Platform stub: MOSS realtime needs request headers, which browser
/// WebSockets cannot set. Native platforms use ws_channel_io.dart.
WebSocketChannel connectVoiceSocket(Uri uri, String token) {
  throw UnsupportedError('实时语音仅支持 iOS / Android 客户端');
}
