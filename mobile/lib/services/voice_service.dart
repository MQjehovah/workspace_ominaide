import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_service.dart';

class VoiceReply {
  final List<int> audio;
  final String transcript;
  final String reply;
  final String mimeType;

  const VoiceReply({
    required this.audio,
    required this.transcript,
    required this.reply,
    required this.mimeType,
  });
}

/// Sends a recorded clip to `/api/chat/voice` and returns the synthesized WAV
/// plus the recognized text and assistant reply.
class VoiceService {
  static final VoiceService _instance = VoiceService._();
  factory VoiceService() => _instance;
  VoiceService._();

  Future<VoiceReply> sendVoice(File audioFile, {String? sessionId}) async {
    final api = ApiService();
    final token = api.token;
    if (token == null || token.isEmpty) {
      throw Exception('请先登录');
    }

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${api.baseUrl}/api/chat/voice'),
    );
    request.headers['Authorization'] = 'Bearer $token';
    request.fields['session_id'] = sessionId ?? 'mobile-voice';
    request.files.add(
      await http.MultipartFile.fromPath(
        'file',
        audioFile.path,
        filename: audioFile.uri.pathSegments.last,
      ),
    );

    final client = http.Client();
    try {
      final streamed = await client
          .send(request)
          .timeout(const Duration(minutes: 2));
      final bytes = <int>[];
      await for (final chunk in streamed.stream.timeout(const Duration(minutes: 2))) {
        bytes.addAll(chunk);
      }
      if (streamed.statusCode != 200) {
        throw Exception(_extractError(bytes));
      }
      final transcript =
          Uri.decodeComponent(streamed.headers['x-transcript'] ?? '');
      final reply = Uri.decodeComponent(streamed.headers['x-reply'] ?? '');
      return VoiceReply(
        audio: bytes,
        transcript: transcript,
        reply: reply,
        mimeType: streamed.headers['content-type'] ?? 'audio/wav',
      );
    } finally {
      client.close();
    }
  }

  String _extractError(List<int> bytes) {
    try {
      final text = utf8.decode(bytes, allowMalformed: true);
      return text.isEmpty ? '语音请求失败' : text;
    } catch (_) {
      return '语音请求失败';
    }
  }
}
