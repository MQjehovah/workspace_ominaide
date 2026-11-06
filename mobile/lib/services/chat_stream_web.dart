// Web implementation of SSE streaming using fetch + ReadableStream.
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

/// Stream chat SSE on web using fetch ReadableStream (true incremental).
Stream<String> streamChatSse(
  Uri uri,
  Map<String, String> headers,
  String body,
) async* {
  final request = <String, dynamic>{
    'method': 'POST',
    'headers': headers,
    'body': body,
  };
  final response = await html.window.fetch(uri.toString(), request);
  if (response.status != 200) {
    throw Exception('Chat stream failed: ${response.status}');
  }
  final reader = response.body?.getReader();
  if (reader == null) throw Exception('No response body');

  final decoder = const Utf8Decoder(allowMalformed: true);
  var buffer = '';
  try {
    while (true) {
      final chunk = await reader
          .read()
          .timeout(const Duration(seconds: 90));
      if (chunk.done) break;
      final value = chunk.value;
      final List<int> bytes = value is Uint8List
          ? value
          : (value is List ? value.cast<int>() : const []);
      buffer += decoder.convert(bytes);
      final lines = buffer.split('\n');
      buffer = lines.removeLast();
      for (final line in lines) {
        final event = _parseLine(line);
        if (event == null) continue;
        if (event.done) return;
        final token = event.token;
        if (token != null && token.isNotEmpty) yield token;
      }
    }
    if (buffer.isNotEmpty) {
      final event = _parseLine(buffer);
      final token = event?.token;
      if (token != null && token.isNotEmpty) yield token;
    }
  } finally {
    reader.releaseLock();
  }
}

class _SseEvent {
  final bool done;
  final String? token;

  const _SseEvent({this.done = false, this.token});
}

_SseEvent? _parseLine(String line) {
  final t = line.trim();
  if (!t.startsWith('data: ')) return null;
  final payload = t.substring(6).trim();
  if (payload == '[DONE]') return const _SseEvent(done: true);

  dynamic obj;
  try {
    obj = jsonDecode(payload);
  } on FormatException {
    return null;
  }
  if (obj is! Map) return null;

  if (obj['type'] == 'error') {
    final message = (obj['content'] ?? '生成失败').toString();
    throw Exception(message);
  }
  if (obj['type'] == 'token') {
    return _SseEvent(token: obj['content'] as String?);
  }
  return null;
}
