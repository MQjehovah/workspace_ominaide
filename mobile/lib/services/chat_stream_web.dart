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
      final chunk = await reader.read();
      if (chunk.done) break;
      final value = chunk.value;
      final List<int> bytes = value is Uint8List ? value : (value is List ? value.cast<int>() : const []);
      buffer += decoder.convert(bytes);
      final lines = buffer.split('\n');
      buffer = lines.removeLast();
      for (final line in lines) {
        final t = line.trim();
        if (!t.startsWith('data: ')) continue;
        final payload = t.substring(6).trim();
        if (payload == '[DONE]') return;
        try {
          final obj = jsonDecode(payload);
          if (obj['type'] == 'token') {
            final content = obj['content'] as String?;
            if (content != null && content.isNotEmpty) yield content;
          }
        } catch (_) {}
      }
    }
    if (buffer.isNotEmpty) {
      final t = buffer.trim();
      if (t.startsWith('data: ') && !t.contains('[DONE]')) {
        try {
          final obj = jsonDecode(t.substring(6).trim());
          if (obj['type'] == 'token') {
            final content = obj['content'] as String?;
            if (content != null && content.isNotEmpty) yield content;
          }
        } catch (_) {}
      }
    }
  } finally {
    reader.releaseLock();
  }
}
