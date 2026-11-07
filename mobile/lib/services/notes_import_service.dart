import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_service.dart';

/// Multipart import for local files (PDF/Word/HTML/text/audio) into notes.
class NotesImportService {
  static final NotesImportService _instance = NotesImportService._();
  factory NotesImportService() => _instance;
  NotesImportService._();

  Future<Map<String, dynamic>> importFile(
    String filePath,
    String filename, {
    int? parentId,
    String? title,
  }) async {
    final api = ApiService();
    final token = api.token;
    if (token == null || token.isEmpty) throw Exception('请先登录');

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${api.baseUrl}/api/plugins/notes/import/file'),
    );
    request.headers['Authorization'] = 'Bearer $token';
    if (parentId != null) request.fields['parent_id'] = '$parentId';
    if (title != null && title.isNotEmpty) request.fields['title'] = title;
    request.files.add(
      await http.MultipartFile.fromPath('file', filePath, filename: filename),
    );

    final client = http.Client();
    try {
      final streamed = await client
          .send(request)
          .timeout(const Duration(minutes: 3));
      final bytes = <int>[];
      await for (final chunk
          in streamed.stream.timeout(const Duration(minutes: 3))) {
        bytes.addAll(chunk);
      }
      if (streamed.statusCode != 201 && streamed.statusCode != 200) {
        throw Exception(_errorText(bytes));
      }
      final decoded = jsonDecode(utf8.decode(bytes, allowMalformed: true));
      if (decoded is Map) {
        return decoded.map((k, v) => MapEntry(k.toString(), v));
      }
      return {};
    } finally {
      client.close();
    }
  }

  String _errorText(List<int> bytes) {
    try {
      final text = utf8.decode(bytes, allowMalformed: true);
      return text.isEmpty ? '导入失败' : text;
    } catch (_) {
      return '导入失败';
    }
  }
}
