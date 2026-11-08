// IO (mobile/desktop) implementation of SSE streaming using http package.
import 'dart:convert';
import 'package:http/http.dart' as http;

/// Stream chat SSE on native platforms.
Stream<String> streamChatSse(
  Uri uri,
  Map<String, String> headers,
  String body,
) async* {
  // Use a dedicated client so cancelling the subscription (stop generating)
  // closes the connection instead of leaving a half-open request behind.
  final client = http.Client();
  try {
    final request = http.Request('POST', uri)
      ..headers.addAll(headers)
      ..body = body;
    final streamed = await client
        .send(request)
        .timeout(const Duration(seconds: 20));
    if (streamed.statusCode != 200) {
      final bytes = await streamed.stream.toBytes();
      throw Exception(_extractError(bytes));
    }

    final lines = streamed.stream
        .timeout(const Duration(minutes: 5))
        .transform(utf8.decoder)
        .transform(const LineSplitter());
    await for (final line in lines) {
      final t = line.trim();
      if (!t.startsWith('data: ')) continue;
      final payload = t.substring(6).trim();
      if (payload == '[DONE]') break;

      dynamic obj;
      try {
        obj = jsonDecode(payload);
      } on FormatException {
        continue;
      }
      if (obj is! Map) continue;

      if (obj['type'] == 'error') {
        final message = (obj['content'] ?? '生成失败').toString();
        throw Exception(message);
      }
      if (obj['type'] == 'token') {
        final content = obj['content'] as String?;
        if (content != null && content.isNotEmpty) yield content;
      }
    }
  } finally {
    client.close();
  }
}

String _extractError(List<int> bytes) {
  try {
    final d = jsonDecode(utf8.decode(bytes));
    final detail = d['detail'];
    if (detail is String) return detail;
    if (d['message'] is String) return d['message'] as String;
  } catch (_) {}
  return 'Request failed';
}
