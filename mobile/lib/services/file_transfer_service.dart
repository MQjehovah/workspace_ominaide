import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'api_service.dart';

/// Streams file downloads to Application Support and uploads from disk with
/// progress callbacks, avoiding loading whole files into memory.
class FileTransferService {
  static final FileTransferService _instance = FileTransferService._();
  factory FileTransferService() => _instance;
  FileTransferService._();

  String _safeName(String name) {
    var base = name.trim().replaceAll(RegExp(r'[\\/:*?"<>|\n\r\t]'), '_');
    if (base.isEmpty) base = 'file';
    return base.length > 120 ? base.substring(base.length - 120) : base;
  }

  Future<File> download(
    int fileId,
    String filename, {
    void Function(int received, int total)? onProgress,
  }) async {
    final request = await ApiService().getFileDownloadRequest(fileId);
    final support = await getApplicationSupportDirectory();
    final dir = Directory('${support.path}/downloads');
    if (!await dir.exists()) await dir.create(recursive: true);
    final target = File('${dir.path}/${fileId}_${_safeName(filename)}');
    final part = File('${target.path}.part');

    final client = http.Client();
    IOSink? sink;
    try {
      final req = http.Request('GET', request.uri);
      req.headers.addAll(request.headers);
      final response =
          await client.send(req).timeout(const Duration(seconds: 30));
      if (response.statusCode != 200) {
        throw Exception('下载失败: ${response.statusCode}');
      }
      final total = response.contentLength ?? 0;
      var received = 0;
      sink = part.openWrite();
      await for (final chunk
          in response.stream.timeout(const Duration(seconds: 120))) {
        sink.add(chunk);
        received += chunk.length;
        onProgress?.call(received, total);
      }
      await sink.flush();
      await sink.close();
      sink = null;
      if (await target.exists()) await target.delete();
      await part.rename(target.path);
      return target;
    } finally {
      try {
        await sink?.close();
      } catch (_) {}
      client.close();
      if (await part.exists()) {
        try {
          await part.delete();
        } catch (_) {}
      }
    }
  }

  Future<Map<String, dynamic>> upload(
    String filePath,
    String filename,
    String folderPath, {
    void Function(int sent, int total)? onProgress,
    int maxAttempts = 3,
  }) async {
    Object? lastError;
    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        return await _uploadOnce(
          filePath,
          filename,
          folderPath,
          onProgress: onProgress,
        );
      } catch (error) {
        lastError = error;
        if (attempt + 1 < maxAttempts) {
          onProgress?.call(0, 0);
          await Future<void>.delayed(
            Duration(seconds: 1 + attempt * 2),
          );
        }
      }
    }
    throw lastError ?? Exception('上传失败');
  }

  Future<Map<String, dynamic>> _uploadOnce(
    String filePath,
    String filename,
    String folderPath, {
    void Function(int sent, int total)? onProgress,
  }) async {
    final api = ApiService();
    final token = api.token;
    if (token == null || token.isEmpty) throw Exception('请先登录');

    final file = File(filePath);
    final total = await file.length();
    var sent = 0;
    final stream = file.openRead().transform(
      StreamTransformer<List<int>, List<int>>.fromHandlers(
        handleData: (chunk, sink) {
          sent += chunk.length;
          onProgress?.call(sent, total);
          sink.add(chunk);
        },
      ),
    );

    final uri = Uri.parse(
      '${api.baseUrl}/api/files/upload/direct'
      '?folder_path=${Uri.encodeComponent(folderPath)}',
    );
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $token'
      ..files.add(
        http.MultipartFile('file', stream, total, filename: filename),
      );

    final client = http.Client();
    try {
      final streamed =
          await client.send(request).timeout(const Duration(minutes: 10));
      final bytes = <int>[];
      await for (final chunk in streamed.stream) {
        bytes.addAll(chunk);
      }
      if (streamed.statusCode != 200) {
        throw Exception('上传失败: ${streamed.statusCode}');
      }
      final text = utf8.decode(bytes, allowMalformed: true);
      if (text.isEmpty) return <String, dynamic>{};
      final decoded = jsonDecode(text);
      return decoded is Map
          ? decoded.map((k, v) => MapEntry(k.toString(), v))
          : <String, dynamic>{};
    } finally {
      client.close();
    }
  }
}
