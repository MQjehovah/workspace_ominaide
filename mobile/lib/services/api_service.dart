import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/file_item.dart';
import '../models/chat_session.dart';
import '../models/cos_models.dart';
import 'chat_stream_stub.dart'
    if (dart.library.html) 'chat_stream_web.dart'
    if (dart.library.io) 'chat_stream_io.dart';
import 'file_save_stub.dart'
    if (dart.library.html) 'file_save_web.dart'
    if (dart.library.io) 'file_save_io.dart';
import '../config.dart';
import 'token_utils.dart';

/// Thin wrapper around a single long-lived [http.Client] so requests reuse
/// connections (TLS handshakes are expensive on mobile) and never hang forever.
class _ApiHttp {
  final http.Client _client = http.Client();
  static const Duration _defaultTimeout = Duration(seconds: 20);
  void Function(int status)? onStatus;
  Future<void> Function()? beforeRequest;
  Future<bool> Function()? refresh;
  String? Function()? accessToken;

  Map<String, String>? _headersFor(Map<String, String>? headers) {
    final next = headers == null ? <String, String>{} : Map.of(headers);
    final token = accessToken?.call();
    if (token != null && token.isNotEmpty) {
      next['Authorization'] = 'Bearer $token';
    } else {
      next.remove('Authorization');
    }
    return next;
  }

  Future<http.Response> _run(
    Future<http.Response> Function() call, {
    bool retry = true,
  }) async {
    await beforeRequest?.call();
    var response = await call();
    if (retry && response.statusCode == 401 && refresh != null) {
      if (await refresh!()) {
        await beforeRequest?.call();
        response = await call();
      }
    }
    onStatus?.call(response.statusCode);
    return response;
  }

  Future<http.Response> get(
    Uri uri, {
    Map<String, String>? headers,
    Duration? timeout,
  }) {
    return _run(() => _client
        .get(uri, headers: _headersFor(headers))
        .timeout(timeout ?? _defaultTimeout));
  }

  Future<http.Response> post(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
    Duration? timeout,
  }) {
    return _run(() => _client
        .post(uri, headers: _headersFor(headers), body: body, encoding: encoding)
        .timeout(timeout ?? _defaultTimeout));
  }

  Future<http.Response> put(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
    Duration? timeout,
  }) {
    return _run(() => _client
        .put(uri, headers: _headersFor(headers), body: body, encoding: encoding)
        .timeout(timeout ?? _defaultTimeout));
  }

  Future<http.Response> delete(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    Duration? timeout,
  }) {
    return _run(() => _client
        .delete(uri, headers: _headersFor(headers), body: body)
        .timeout(timeout ?? _defaultTimeout));
  }

  Future<http.Response> patch(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
    Duration? timeout,
  }) {
    return _run(() => _client
        .patch(uri, headers: _headersFor(headers), body: body, encoding: encoding)
        .timeout(timeout ?? _defaultTimeout));
  }

  Future<http.StreamedResponse> send(
    http.BaseRequest request, {
    Duration? timeout,
  }) async {
    await beforeRequest?.call();
    final token = accessToken?.call();
    if (token != null && token.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    final response =
        await _client.send(request).timeout(timeout ?? _defaultTimeout);
    onStatus?.call(response.statusCode);
    return response;
  }
}

class ApiService {
  static const _tokenKey = 'omniaide.token';
  static const _refreshTokenKey = 'omniaide.refresh_token';
  final _http = _ApiHttp();
  final _secure = const FlutterSecureStorage();
  String _baseUrl = kDefaultServerUrl;
  String? _token;
  String? _refreshToken;
  bool _handlingUnauthorized = false;
  Future<bool>? _refreshing;

  /// Set by main() to route back to the login screen when the session expires.
  void Function()? onUnauthorized;

  static final ApiService _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._() {
    _http.onStatus = _handleStatus;
    _http.beforeRequest = _ensureFreshToken;
    _http.refresh = _refreshAccessToken;
    _http.accessToken = () => _token;
  }

  String get baseUrl => _baseUrl;
  String? get token => _token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Map<String, String> get _authHeaders => {
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  void _handleStatus(int status) {
    if (status != 401 || _handlingUnauthorized) return;
    if (_token == null || _token!.isEmpty) return;
    _handlingUnauthorized = true;
    _token = null;
    _refreshToken = null;
    _clearStoredToken();
    onUnauthorized?.call();
  }

  Future<void> _ensureFreshToken() async {
    if (_token == null || _token!.isEmpty) return;
    if (!tokenNeedsRefresh(_token)) return;
    await _refreshAccessToken();
  }

  Future<bool> _refreshAccessToken() {
    final existing = _refreshing;
    if (existing != null) return existing;
    final future = _doRefresh();
    _refreshing = future;
    future.whenComplete(() => _refreshing = null);
    return future;
  }

  Future<bool> _doRefresh() async {
    final refresh = _refreshToken ?? await _readStoredRefreshToken();
    if (refresh == null || refresh.isEmpty) return false;
    try {
      final res = await http.post(
        Uri.parse('$_baseUrl/api/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refresh}),
      ).timeout(const Duration(seconds: 20));
      if (res.statusCode != 200) return false;
      final data = decodeJson(res);
      final access = data['access_token'];
      final nextRefresh = data['refresh_token'];
      if (access is! String || access.isEmpty) return false;
      _token = access;
      _refreshToken = nextRefresh is String && nextRefresh.isNotEmpty
          ? nextRefresh
          : refresh;
      _handlingUnauthorized = false;
      await _writeStoredToken(access);
      await _writeStoredRefreshToken(_refreshToken!);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<String?> _readStoredToken() async {
    try {
      final value = await _secure.read(key: _tokenKey);
      if (value != null && value.isNotEmpty) return value;
    } catch (_) {}
    return null;
  }

  Future<void> _writeStoredToken(String token) async {
    try {
      await _secure.write(key: _tokenKey, value: token);
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('token');
    } catch (_) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('token', token);
    }
  }

  Future<String?> _readStoredRefreshToken() async {
    try {
      final value = await _secure.read(key: _refreshTokenKey);
      if (value != null && value.isNotEmpty) return value;
    } catch (_) {}
    return null;
  }

  Future<void> _writeStoredRefreshToken(String token) async {
    try {
      await _secure.write(key: _refreshTokenKey, value: token);
    } catch (_) {}
  }

  Future<void> _clearStoredToken() async {
    try {
      await _secure.delete(key: _tokenKey);
      await _secure.delete(key: _refreshTokenKey);
    } catch (_) {}
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('token');
  }

  Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    var token = await _readStoredToken();
    if (token == null) {
      // Migrate the token saved by older versions in plain SharedPreferences.
      final legacy = prefs.getString('token');
      if (legacy != null && legacy.isNotEmpty) {
        token = legacy;
        await _writeStoredToken(legacy);
      }
    }
    _token = token;
    _refreshToken = await _readStoredRefreshToken();
    _handlingUnauthorized = false;
    final stored = prefs.getString('serverUrl');
    // Migrate the old, unreachable default (port 8000) to the new API prefix.
    if (stored == null ||
        stored.isEmpty ||
        stored == 'http://mqgeek.com:8000') {
      _baseUrl = kDefaultServerUrl;
      await prefs.setString('serverUrl', _baseUrl);
    } else {
      _baseUrl = normalizeServerUrl(stored);
    }
  }

  /// Persist a new server address. The currently stored token is not cleared;
  /// callers should ask the user to log in again when the server changes.
  Future<void> setServerUrl(String serverUrl) async {
    _baseUrl = normalizeServerUrl(serverUrl);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('serverUrl', _baseUrl);
  }

  Future<void> saveAuth(
    String token,
    String serverUrl, {
    String? refreshToken,
  }) async {
    _token = token;
    _refreshToken = refreshToken;
    _handlingUnauthorized = false;
    _baseUrl = normalizeServerUrl(serverUrl);
    await _writeStoredToken(token);
    if (refreshToken != null && refreshToken.isNotEmpty) {
      await _writeStoredRefreshToken(refreshToken);
    } else {
      try {
        await _secure.delete(key: _refreshTokenKey);
      } catch (_) {}
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('serverUrl', _baseUrl);
  }

  Future<void> logout() async {
    _token = null;
    _refreshToken = null;
    _handlingUnauthorized = false;
    await _clearStoredToken();
    // Keep serverUrl so the next login pre-fills the server the user chose.
  }

  bool get isLoggedIn => _token != null;

  Future<String> login(
      String serverUrl, String username, String password) async {
    final res = await _http.post(
      Uri.parse('$serverUrl/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );
    if (res.statusCode != 200) {
      final detail = decodeJson(res);
      throw Exception(detail['detail'] ?? 'Login failed');
    }
    final data = decodeJson(res);
    await saveAuth(
      data['access_token'],
      serverUrl,
      refreshToken: data['refresh_token'],
    );
    return data['access_token'];
  }

  // -- Files --
  Future<List<FileItem>> listFiles({
    String folderPath = '/',
    String? search,
  }) async {
    final params = <String, String>{'page_size': '100'};
    if (search == null || search.isEmpty) {
      params['folder_path'] = folderPath;
    } else {
      params['search'] = search;
    }
    final uri =
        Uri.parse('$_baseUrl/api/files').replace(queryParameters: params);
    final res = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    return (data['files'] as List).map((f) => FileItem.fromJson(f)).toList();
  }

  Future<Map<String, dynamic>> shareFileLink(
    int fileId, {
    int expiresHours = 168,
  }) async {
    final res = await post(
      '/files/$fileId/share?expires_hours=$expiresHours',
      const {},
    );
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  // -- Vibecoding --
  Future<List<dynamic>> listVibecodingTasks({int limit = 50}) async {
    try {
      final res = await _http.get(
        Uri.parse('$_baseUrl/api/vibecoding/tasks?limit=$limit'),
        headers: _authHeaders,
      );
      if (res.statusCode != 200) return [];
      final data = decodeJson(res);
      return (data['tasks'] as List?) ?? [];
    } catch (_) {
      return [];
    }
  }

  Future<void> renameVibecodingMachine(String machineId, String name) async {
    final res = await put('/vibecoding/machines/$machineId', {'name': name});
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<List<dynamic>> listVibecodingMachines() async {
    try {
      final res = await _http.get(
        Uri.parse('$_baseUrl/api/vibecoding/machines'),
        headers: _authHeaders,
      );
      if (res.statusCode != 200) return [];
      final data = decodeJson(res);
      if (data is List) return data;
      return (data['machines'] as List?) ?? [];
    } catch (_) {
      return [];
    }
  }

  /// Download file bytes through backend proxy (or presigned URL).
  Future<List<int>> downloadFile(int fileId) async {
    final dlRes = await _http.get(
      Uri.parse('$_baseUrl/api/files/$fileId/download-url'),
      headers: _headers,
    );
    if (dlRes.statusCode != 200) throw Exception('Failed to get download info');
    final dlData = decodeJson(dlRes);
    final dlUrl = dlData['download_url'] as String?;

    if (dlUrl != null && dlUrl.isNotEmpty) {
      final res = await _http.get(
        Uri.parse(dlUrl),
        timeout: const Duration(minutes: 5),
      );
      if (res.statusCode != 200)
        throw Exception('Download failed: ${res.statusCode}');
      return res.bodyBytes;
    } else {
      final res = await _http.get(
        Uri.parse('$_baseUrl/api/files/$fileId/download'),
        headers: _authHeaders,
        timeout: const Duration(minutes: 5),
      );
      if (res.statusCode != 200)
        throw Exception('Download failed: ${res.statusCode}');
      return res.bodyBytes;
    }
  }

  /// Resolve the real download URL and headers without loading the bytes.
  /// Used by the music cache to stream large files to disk.
  Future<({Uri uri, Map<String, String> headers})> getFileDownloadRequest(
      int fileId) async {
    final dlRes = await _http.get(
      Uri.parse('$_baseUrl/api/files/$fileId/download-url'),
      headers: _headers,
    );
    if (dlRes.statusCode != 200) throw Exception('Failed to get download info');
    final dlData = decodeJson(dlRes);
    final dlUrl = dlData['download_url'] as String?;
    if (dlUrl != null && dlUrl.isNotEmpty) {
      return (uri: Uri.parse(dlUrl), headers: <String, String>{});
    }
    return (
      uri: Uri.parse('$_baseUrl/api/files/$fileId/download'),
      headers: _authHeaders,
    );
  }

  /// Save downloaded bytes to local file, returns the file path.
  Future<String> saveFileLocally(int fileId, String filename) async {
    final bytes = await downloadFile(fileId);
    final out = await writeBytesLocal(filename, bytes);
    return out;
  }

  /// Upload file directly through backend proxy.
  Future<void> uploadFileDirect(
      String filePath, String filename, String folderPath) async {
    final uri = Uri.parse(
        '$_baseUrl/api/files/upload/direct?folder_path=${Uri.encodeComponent(folderPath)}');
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_authHeaders)
      ..files.add(await http.MultipartFile.fromPath('file', filePath,
          filename: filename));
    final streamed = await _http.send(
      request,
      timeout: const Duration(minutes: 10),
    );
    if (streamed.statusCode != 200)
      throw Exception('Upload failed: ${streamed.statusCode}');
  }

  // -- Meeting minutes --
  Future<Map<String, dynamic>> createMeetingMinutes({
    required int fileId,
    String? title,
    int? eventId,
    String? language,
  }) async {
    final res = await post('/meetings/minutes', {
      'file_id': fileId,
      if (title != null && title.isNotEmpty) 'title': title,
      if (eventId != null) 'event_id': eventId,
      if (language != null) 'language': language,
    });
    if (res.statusCode != 202 && res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> getMeetingMinutes(int id) async {
    final res = await get('/meetings/minutes/$id');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> listMeetingMinutes(
      {int limit = 30}) async {
    final res = await get('/meetings/minutes?limit=$limit');
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    final list = data is Map ? (data['items'] as List? ?? const []) : const [];
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<void> retryMeetingMinutes(int id) async {
    final res = await post('/meetings/minutes/$id/retry', const {});
    if (res.statusCode != 202 && res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
  }

  Future<void> deleteMeetingMinutes(int id, {bool deleteAudio = true}) async {
    final res = await delete(
      '/meetings/minutes/$id?delete_audio=$deleteAudio',
    );
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<Map<String, dynamic>> getUploadUrl(
      String filename, String folderPath) async {
    final res = await _http.post(
      Uri.parse('$_baseUrl/api/files/upload-url'),
      headers: _headers,
      body: jsonEncode({'filename': filename, 'folder_path': folderPath}),
    );
    if (res.statusCode != 200) throw Exception('Failed to get upload URL');
    return decodeJson(res);
  }

  Future<void> confirmUpload(int fileId) async {
    await _http.post(
      Uri.parse('$_baseUrl/api/files/confirm'),
      headers: _headers,
      body: jsonEncode({'file_id': fileId}),
    );
  }

  Future<FileItem> createFolder(String name, String parentPath) async {
    final res = await _http.post(
      Uri.parse('$_baseUrl/api/files/folder'),
      headers: _headers,
      body: jsonEncode({'name': name, 'parent_path': parentPath}),
    );
    if (res.statusCode != 201) throw Exception('Failed to create folder');
    return FileItem.fromJson(decodeJson(res));
  }

  // -- Notes --
  /// Parse ProseMirror JSON content to plain text for mobile display.
  String parseNoteContent(String raw) {
    if (raw.isEmpty) return '';
    // Try JSON (ProseMirror format)
    try {
      final doc = jsonDecode(raw);
      if (doc is Map && doc['type'] == 'doc' && doc['content'] is List) {
        final buffer = StringBuffer();
        _extractText(doc['content'] as List, buffer);
        return buffer.toString().trim();
      }
    } catch (_) {}
    return raw; // plain text fallback
  }

  /// Build a minimal valid ProseMirror document from plain text.
  /// Mobile edits preserve the document shape instead of saving raw text.
  String plainTextToNoteJson(String text) {
    final paragraphs = text.split('\n').map((line) {
      final node = <String, dynamic>{'type': 'paragraph'};
      if (line.isNotEmpty) {
        node['content'] = [
          {'type': 'text', 'text': line},
        ];
      }
      return node;
    }).toList();
    return jsonEncode({'type': 'doc', 'content': paragraphs});
  }

  /// Return Markdown for a note body. The web editor stores Markdown via
  /// `getMarkdown()`, while older notes may still be ProseMirror JSON.
  String parseNoteMarkdown(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    try {
      final doc = jsonDecode(text);
      if (doc is Map && doc['type'] == 'doc' && doc['content'] is List) {
        return _proseMirrorToMarkdown(doc['content'] as List).trim();
      }
    } catch (_) {}
    return raw;
  }

  String _proseMirrorToMarkdown(List nodes, {int depth = 0}) {
    final out = StringBuffer();
    for (final raw in nodes) {
      if (raw is! Map) continue;
      final node = raw.map((k, v) => MapEntry(k.toString(), v));
      final type = node['type']?.toString() ?? '';
      final content =
          node['content'] is List ? node['content'] as List : const [];

      if (type == 'text') {
        out.write(_markedText(node));
      } else if (type == 'paragraph') {
        out.write(_inlineMarkdown(content));
        out.write('\n\n');
      } else if (type == 'heading') {
        final level = (node['attrs']?['level'] as int?) ?? 1;
        final hashes = '#' * level.clamp(1, 6);
        out.write('$hashes ${_inlineMarkdown(content)}\n\n');
      } else if (type == 'bulletList') {
        for (final item in content) {
          if (item is! Map) continue;
          final body = _proseMirrorToMarkdown(
            item['content'] is List ? item['content'] as List : const [],
            depth: depth + 1,
          ).trim().replaceAll('\n', '\n${'  ' * (depth + 1)}');
          out.writeln('${'  ' * depth}- $body');
        }
        out.writeln();
      } else if (type == 'orderedList') {
        var index = 1;
        for (final item in content) {
          if (item is! Map) continue;
          final body = _proseMirrorToMarkdown(
            item['content'] is List ? item['content'] as List : const [],
            depth: depth + 1,
          ).trim().replaceAll('\n', '\n${'  ' * (depth + 1)}');
          out.writeln('${'  ' * depth}$index. $body');
          index++;
        }
        out.writeln();
      } else if (type == 'listItem') {
        out.write(_proseMirrorToMarkdown(content, depth: depth));
      } else if (type == 'blockquote') {
        final inner = _proseMirrorToMarkdown(content, depth: depth).trim();
        for (final line in inner.split('\n')) {
          out.writeln('> $line');
        }
        out.writeln();
      } else if (type == 'codeBlock') {
        final language = (node['attrs']?['language'] ?? '').toString();
        final code = content
            .whereType<Map>()
            .map((e) => (e['text'] ?? '').toString())
            .join();
        out.writeln('```$language');
        out.writeln(code);
        out.writeln('```\n');
      } else if (type == 'hardBreak') {
        out.write('  \n');
      } else if (type == 'horizontalRule') {
        out.write('\n---\n\n');
      } else if (type == 'image') {
        final src = (node['attrs']?['src'] ?? '').toString();
        final alt = (node['attrs']?['alt'] ?? '').toString();
        out.write('![$alt]($src)');
      } else if (type == 'table') {
        final rows = content.whereType<Map>().toList();
        for (var i = 0; i < rows.length; i++) {
          final cells = (rows[i]['content'] is List)
              ? (rows[i]['content'] as List).whereType<Map>().toList()
              : const <Map>[];
          final values = cells
              .map((cell) => _proseMirrorToMarkdown(
                    cell['content'] is List
                        ? cell['content'] as List
                        : const [],
                    depth: depth,
                  ).trim().replaceAll('\n', ' '))
              .toList();
          out.writeln('| ${values.join(' | ')} |');
          if (i == 0) {
            out.writeln('| ${values.map((_) => '---').join(' | ')} |');
          }
        }
        out.writeln();
      } else {
        out.write(_proseMirrorToMarkdown(content, depth: depth));
      }
    }
    return out.toString();
  }

  String _inlineMarkdown(List nodes) {
    final out = StringBuffer();
    for (final raw in nodes) {
      if (raw is! Map) continue;
      final node = raw.map((k, v) => MapEntry(k.toString(), v));
      final type = node['type']?.toString() ?? '';
      if (type == 'text') {
        out.write(_markedText(node));
      } else if (type == 'hardBreak') {
        out.write('  \n');
      } else if (type == 'image') {
        final src = (node['attrs']?['src'] ?? '').toString();
        final alt = (node['attrs']?['alt'] ?? '').toString();
        out.write('![$alt]($src)');
      } else if (node['content'] is List) {
        out.write(_inlineMarkdown(node['content'] as List));
      }
    }
    return out.toString();
  }

  String _markedText(Map<String, dynamic> node) {
    var text = (node['text'] ?? '').toString();
    final marks = (node['marks'] as List? ?? []).whereType<Map>();
    for (final rawMark in marks) {
      final mark = rawMark.map((k, v) => MapEntry(k.toString(), v));
      final type = mark['type']?.toString() ?? '';
      if (type == 'bold') {
        text = '**$text**';
      } else if (type == 'italic') {
        text = '*$text*';
      } else if (type == 'code') {
        text = '`$text`';
      } else if (type == 'strike') {
        text = '~~$text~~';
      } else if (type == 'link') {
        final href = (mark['attrs']?['href'] ?? '').toString();
        if (href.isNotEmpty) text = '[$text]($href)';
      }
    }
    return text;
  }

  void _extractText(List nodes, StringBuffer buffer) {
    for (final node in nodes) {
      if (node is! Map) continue;
      if (node['type'] == 'text' && node['text'] is String) {
        buffer.write(node['text']);
      }
      if (node['type'] == 'paragraph') {
        if (buffer.isNotEmpty && !buffer.toString().endsWith('\n'))
          buffer.writeln();
      }
      if (node['type'] == 'heading') {
        if (buffer.isNotEmpty) buffer.writeln();
        buffer.write('${'#' * ((node['attrs']?['level'] as int?) ?? 1)} ');
      }
      if (node['content'] is List) {
        _extractText(node['content'] as List, buffer);
      }
      if (node['type'] == 'paragraph' || node['type'] == 'heading') {
        buffer.writeln();
      }
      // Tables: extract cell text
      if (node['type'] == 'table') {
        if (node['content'] is List) {
          for (final row in node['content'] as List) {
            if (row is Map &&
                row['type'] == 'tableRow' &&
                row['content'] is List) {
              for (final cell in row['content'] as List) {
                if (cell is Map && cell['content'] is List) {
                  _extractText(cell['content'] as List, buffer);
                  buffer.write(' | ');
                }
              }
              buffer.writeln();
            }
          }
        }
      }
    }
  }

  // -- REST --
  /// Decode response body as UTF-8 (http package defaults to latin1 when charset missing).
  dynamic decodeJson(http.Response res) {
    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  Future<http.Response> get(String path) async {
    return await _http.get(Uri.parse('$_baseUrl/api$path'), headers: _headers);
  }

  Future<http.Response> post(String path, Map<String, dynamic> body) async {
    return await _http.post(
      Uri.parse('$_baseUrl/api$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
  }

  Future<http.Response> put(String path, Map<String, dynamic> body) async {
    return await _http.put(
      Uri.parse('$_baseUrl/api$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
  }

  Future<http.Response> delete(String path) async {
    return await _http.delete(Uri.parse('$_baseUrl/api$path'),
        headers: _headers);
  }

  Future<http.Response> patch(String path, Map<String, dynamic> body) async {
    return await _http.patch(
      Uri.parse('$_baseUrl/api$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
  }

  // -- Chat --
  Future<String> chat(String message,
      {List<Map<String, String>>? history,
      bool agent = false,
      String? sessionId}) async {
    final path = agent ? '/api/chat/agent' : '/api/chat';
    final res = await _http.post(
      Uri.parse('$_baseUrl$path'),
      headers: _headers,
      body: jsonEncode({
        'message': message,
        'history': history ?? [],
        if (sessionId != null) 'session_id': sessionId,
      }),
      timeout: const Duration(minutes: 2),
    );
    if (res.statusCode != 200) {
      final detail = _extractError(res);
      throw Exception(detail);
    }
    final data = decodeJson(res);
    return (data['reply'] as String?) ?? '';
  }

  /// Stream chat via SSE (incremental on all platforms).
  Stream<String> chatStream(String message,
      {List<Map<String, String>>? history, String? sessionId, int? botId}) {
    final path = '/api/chat/stream';
    final uri = Uri.parse('$_baseUrl$path');
    final headers = <String, String>{..._headers};
    final body = jsonEncode({
      'message': message,
      'history': history ?? [],
      if (sessionId != null) 'session_id': sessionId,
      if (botId != null) 'bot_id': botId,
    });
    return streamChatSse(uri, headers, body);
  }

  /// Load persisted chat history so the mobile client shares context with Web/desktop.
  Future<List<Map<String, dynamic>>> loadChatHistory(
      {String? sessionId, int limit = 50, int? beforeId}) async {
    final q = <String, String>{'limit': '$limit'};
    if (sessionId != null) q['session_id'] = sessionId;
    if (beforeId != null) q['before_id'] = '$beforeId';
    final uri =
        Uri.parse('$_baseUrl/api/chat/history').replace(queryParameters: q);
    final res = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) return [];
    final dynamic d = decodeJson(res);
    if (d is! List) return [];
    return d.cast<Map<String, dynamic>>();
  }

  String _extractError(http.Response res) {
    try {
      final d = jsonDecode(utf8.decode(res.bodyBytes));
      final detail = d['detail'];
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) return detail.toString();
      if (d['message'] is String) return d['message'] as String;
    } catch (_) {}
    return 'Request failed';
  }

  // -- Schedule --
  Future<List<Map<String, dynamic>>> listScheduleEvents(
      {String? start, String? end}) async {
    final q = <String, String>{};
    if (start != null) q['start'] = start;
    if (end != null) q['end'] = end;
    final uri = Uri.parse('$_baseUrl/api/schedule')
        .replace(queryParameters: q.isEmpty ? null : q);
    final res = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) return [];
    final d = decodeJson(res);
    return (d as List? ?? []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createScheduleEvent(
      Map<String, dynamic> data) async {
    final res = await _http.post(Uri.parse('$_baseUrl/api/schedule'),
        headers: _headers, body: jsonEncode(data));
    if (res.statusCode != 201 && res.statusCode != 200)
      throw Exception(_extractError(res));
    return decodeJson(res);
  }

  Future<Map<String, dynamic>> updateScheduleEvent(
    int eventId,
    Map<String, dynamic> data,
  ) async {
    final res = await put('/schedule/$eventId', data);
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<void> deleteScheduleEvent(int id) async {
    await _http.delete(Uri.parse('$_baseUrl/api/schedule/$id'),
        headers: _headers);
  }

  // -- Todo --
  Future<List<Map<String, dynamic>>> listTodoItems(
      {String? status, int pageSize = 50}) async {
    final q = <String, String>{'page_size': '$pageSize'};
    if (status != null) q['status'] = status;
    final uri = Uri.parse('$_baseUrl/api/plugins/todo/items')
        .replace(queryParameters: q);
    final res = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) return [];
    final dynamic d = decodeJson(res);
    final List list = d is List
        ? d
        : (d is Map && d['items'] is List ? d['items'] as List : const []);
    return list.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createTodoItem(Map<String, dynamic> data) async {
    final res = await _http.post(Uri.parse('$_baseUrl/api/plugins/todo/items'),
        headers: _headers, body: jsonEncode(data));
    if (res.statusCode != 201 && res.statusCode != 200)
      throw Exception(_extractError(res));
    return decodeJson(res);
  }

  Future<void> updateTodoItem(int id, Map<String, dynamic> data) async {
    await _http.put(Uri.parse('$_baseUrl/api/plugins/todo/items/$id'),
        headers: _headers, body: jsonEncode(data));
  }

  Future<void> deleteTodoItem(int id) async {
    await _http.delete(Uri.parse('$_baseUrl/api/plugins/todo/items/$id'),
        headers: _headers);
  }

  // -- Notifications --
  Future<List<Map<String, dynamic>>> listNotifications({int limit = 20}) async {
    final res = await http
        .get(Uri.parse('$_baseUrl/api/notifications?limit=$limit'),
            headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (res.statusCode != 200) return [];
    final dynamic d = decodeJson(res);
    if (d is! List) return [];
    return d.cast<Map<String, dynamic>>();
  }

  Future<void> markNotificationsRead() async {
    await _http.put(Uri.parse('$_baseUrl/api/notifications/read-all'),
        headers: _headers, body: '{}');
  }

  Future<void> markNotificationRead(int id) async {
    await _http.put(
      Uri.parse('$_baseUrl/api/notifications/$id/read'),
      headers: _headers,
      body: '{}',
    );
  }

  /// Execute an inline notification action (complete_todo / snooze / open).
  Future<Map<String, dynamic>> actOnNotification(int id, String action) async {
    final res = await _http.post(
      Uri.parse('$_baseUrl/api/notifications/$id/action'),
      headers: _headers,
      body: jsonEncode({'action': action}),
    );
    if (res.statusCode != 200) return {};
    return decodeJson(res) as Map<String, dynamic>;
  }

  // -- MCP --
  Future<String> callMCP(String toolName, Map<String, dynamic> args) async {
    final res = await _http.post(
      Uri.parse('$_baseUrl/api/mcp/call'),
      headers: _headers,
      body: jsonEncode({'name': toolName, 'arguments': args}),
    );
    if (res.statusCode != 200) return 'Error: ${res.statusCode}';
    final data = decodeJson(res);
    return data['content']?[0]?['text'] ?? 'No response';
  }

  // -- Search --
  Future<Map<String, dynamic>> searchAll(String query) async {
    final result = <String, dynamic>{
      'files': <FileItem>[],
      'items': <Map<String, dynamic>>[],
      'semantic': <Map<String, dynamic>>[],
    };
    try {
      final filesRes = await _http.get(
        Uri.parse(
            '$_baseUrl/api/files?search=${Uri.encodeComponent(query)}&page_size=10'),
        headers: _headers,
      );
      if (filesRes.statusCode == 200) {
        final data = decodeJson(filesRes);
        result['files'] = (data['files'] as List? ?? [])
            .map((f) => FileItem.fromJson(f))
            .where((f) => !f.isFolder)
            .toList();
      }
    } catch (_) {}
    try {
      final sourcesRes = await _http.get(
        Uri.parse(
            '$_baseUrl/api/sources/search?q=${Uri.encodeComponent(query)}&page_size=10'),
        headers: _headers,
      );
      if (sourcesRes.statusCode == 200) {
        final data = decodeJson(sourcesRes);
        result['items'] =
            (data['items'] as List? ?? []).cast<Map<String, dynamic>>();
      }
    } catch (_) {}
    try {
      final semRes = await _http.post(
        Uri.parse('$_baseUrl/api/search'),
        headers: _headers,
        body: jsonEncode({'q': query, 'top_k': 5}),
      );
      if (semRes.statusCode == 200) {
        final data = decodeJson(semRes);
        result['semantic'] =
            (data['results'] as List? ?? []).cast<Map<String, dynamic>>();
      }
    } catch (_) {}
    return result;
  }

  // -- Audio --
  Future<List<FileItem>> listAudioFiles() async {
    final res = await _http.get(
      Uri.parse('$_baseUrl/api/files?page_size=200'),
      headers: _headers,
    );
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    final audioMimes = [
      'audio/mpeg',
      'audio/mp3',
      'audio/wav',
      'audio/flac',
      'audio/ogg',
      'audio/aac',
      'audio/wma',
      'audio/x-m4a'
    ];
    final audioExts = ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma'];
    return (data['files'] as List)
        .map((f) => FileItem.fromJson(f))
        .where((f) =>
            !f.isFolder &&
            (audioMimes.contains(f.mimeType) ||
                audioExts
                    .contains(f.originalName.split('.').last.toLowerCase())))
        .toList();
  }

  // -- Playlists --
  Future<List<Map<String, dynamic>>> listPlaylists() async {
    final res = await _http.get(Uri.parse('$_baseUrl/api/music/playlists'),
        headers: _headers);
    if (res.statusCode != 200) return [];
    return ((decodeJson(res)['playlists'] as List?) ?? [])
        .cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createPlaylist(String name) async {
    final res = await _http.post(Uri.parse('$_baseUrl/api/music/playlists'),
        headers: _headers, body: jsonEncode({'name': name}));
    if (res.statusCode != 201) throw Exception('Failed to create playlist');
    return decodeJson(res);
  }

  Future<void> deletePlaylist(int id) async {
    await _http.delete(Uri.parse('$_baseUrl/api/music/playlists/$id'),
        headers: _headers);
  }

  Future<List<Map<String, dynamic>>> listPlaylistSongs(int playlistId) async {
    final res = await _http.get(
        Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs'),
        headers: _headers);
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    return (data['songs'] as List?)?.cast<Map<String, dynamic>>() ?? [];
  }

  Future<void> addSongToPlaylist(int playlistId, int fileId) async {
    final res = await _http.post(
        Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs'),
        headers: _headers,
        body: jsonEncode({'file_id': fileId}));
    if (res.statusCode != 201) throw Exception('Failed to add song');
  }

  Future<void> removeSongFromPlaylist(int playlistId, int itemId) async {
    await _http.delete(
        Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs/$itemId'),
        headers: _headers);
  }

  // -- Chat sessions --
  Future<List<ChatSession>> listChatSessions({int? botId}) async {
    final q = <String, String>{};
    if (botId != null) q['bot_id'] = '$botId';
    final uri = Uri.parse('$_baseUrl/api/chat/sessions')
        .replace(queryParameters: q.isEmpty ? null : q);
    final res = await _http.get(uri, headers: _headers);
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) =>
            ChatSession.fromJson(e.map((k, v) => MapEntry(k.toString(), v))))
        .where((s) => s.id.isNotEmpty)
        .toList();
  }

  Future<bool> renameChatSession(String sessionId, String title) async {
    final res = await patch('/chat/sessions/$sessionId', {'title': title});
    return res.statusCode == 200;
  }

  Future<bool> deleteChatSession(String sessionId) async {
    final res = await delete('/chat/sessions/$sessionId');
    return res.statusCode == 200;
  }

  // -- Agent Skills --
  Future<List<Map<String, dynamic>>> listBotSkills(int botId) async {
    final res = await get('/bots/$botId/skills');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(_asMap(decodeJson(res))['skills']);
  }

  Future<void> setBotSkill(int botId, String key, bool enabled) async {
    final res = await put('/bots/$botId/skills/$key', {'enabled': enabled});
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<Map<String, dynamic>> runSkill(
    String key, {
    int? botId,
    Map<String, dynamic> input = const {},
  }) async {
    final res = await post('/skills/$key/run', {
      if (botId != null) 'bot_id': botId,
      'input': input,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  // -- Briefing surfaces (powered by Agent Skills) --
  Future<DailyBrief?> getDailyBrief({int? botId}) async {
    try {
      final res = await post('/skills/daily-brief/run', {
        if (botId != null) 'bot_id': botId,
        'input': <String, dynamic>{},
      });
      if (res.statusCode == 200) {
        final data = _asMap(decodeJson(res));
        return DailyBrief.fromJson(_asMap(data['output']));
      }
      // Transitional fallback while the backend is being upgraded. Remove once
      // every deployment runs the Agent Skills API.
      if (res.statusCode == 404) {
        final legacy = await get('/cos/daily-brief');
        if (legacy.statusCode == 200) {
          return DailyBrief.fromJson(_asMap(decodeJson(legacy)));
        }
      }
    } catch (_) {}
    return null;
  }

  /// Generate and store this week's review (explicit user action).
  Future<WeeklyReview?> runWeeklyReview({int weeks = 1}) async {
    try {
      final res = await post('/insights/weekly/run', {
        'weeks': weeks,
        'force': true,
        'notify': false,
      });
      if (res.statusCode == 200) {
        return WeeklyReview.fromJson(_asMap(decodeJson(res)));
      }
    } catch (_) {}
    return null;
  }

  Future<TriageSnapshot?> getTriage({int days = 3}) async {
    try {
      var res = await get('/inbox/groups?days=$days');
      if (res.statusCode == 404) {
        res = await get('/cos/triage?days=$days');
      }
      if (res.statusCode != 200) return null;
      final data = decodeJson(res);
      if (data is! Map) return null;
      return TriageSnapshot.fromJson(
        data.map((k, v) => MapEntry(k.toString(), v)),
      );
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> getDraftReply({
    String source = 'mail',
    int? messageId,
    String? message,
    String? subject,
    String tone = 'professional',
    int? botId,
  }) async {
    if (messageId == null) return null;
    try {
      var res = await post(
        '/plugins/mail/messages/$messageId/ai-draft',
        {
          'tone': tone,
          if (botId != null) 'bot_id': botId,
        },
      );
      if (res.statusCode == 404) {
        res = await post('/cos/draft-reply', {
          'source': source,
          'message_id': messageId,
          'tone': tone,
        });
      }
      if (res.statusCode != 200) return null;
      final dynamic data = decodeJson(res);
      return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
    } catch (_) {
      return null;
    }
  }

  // -- Mail --
  Future<List<Map<String, dynamic>>> listMailMessages({
    int limit = 50,
    String folder = 'inbox',
    bool unread = false,
  }) async {
    final res = await get(
      '/plugins/mail/messages?page_size=$limit&folder=$folder&unread=$unread',
    );
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    final List list = data is Map
        ? (data['items'] as List? ?? const [])
        : (data is List ? data : const []);
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<List<Map<String, dynamic>>> listMailAccounts() async {
    final res = await get('/plugins/mail/accounts');
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<Map<String, dynamic>> sendMail({
    int? accountId,
    required List<String> to,
    List<String> cc = const [],
    List<String> bcc = const [],
    required String subject,
    required String body,
    int? replyToId,
    List<int> attachmentFileIds = const [],
  }) async {
    final res = await post('/plugins/mail/messages/send', {
      if (accountId != null) 'account_id': accountId,
      'to': to,
      'cc': cc,
      'bcc': bcc,
      'subject': subject,
      'body': body,
      if (replyToId != null) 'reply_to_id': replyToId,
      'attachment_file_ids': attachmentFileIds,
    });
    if (res.statusCode != 200 && res.statusCode != 201) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  Future<int> markAllMailRead() async {
    final res = await put('/plugins/mail/messages/read-all', const {});
    if (res.statusCode != 200) return 0;
    final data = decodeJson(res);
    if (data is Map) {
      final value = data['updated'];
      return value is int ? value : int.tryParse('$value') ?? 0;
    }
    return 0;
  }

  Future<Map<String, dynamic>?> getMailMessage(int id) async {
    final res = await get('/plugins/mail/messages/$id');
    if (res.statusCode != 200) return null;
    final dynamic data = decodeJson(res);
    return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
  }

  // -- Memory --
  Future<List<Map<String, dynamic>>> listMemoryCandidates(
      {String status = 'pending'}) async {
    final res = await get('/memory/candidates?status=$status&limit=100');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    final list = data is Map ? (data['items'] as List? ?? const []) : const [];
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<List<Map<String, dynamic>>> listMemoryRecords() async {
    final res = await get('/memory/records?limit=100');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    final list = data is Map ? (data['items'] as List? ?? const []) : const [];
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<bool> approveMemory(int id) async {
    final res = await post('/memory/candidates/$id/approve', const {});
    return res.statusCode == 200;
  }

  Future<bool> rejectMemory(int id) async {
    final res = await post('/memory/candidates/$id/reject', const {});
    return res.statusCode == 200;
  }

  Future<bool> forgetMemory(int id) async {
    final res = await delete('/memory/records/$id');
    return res.statusCode == 200;
  }

  Future<bool> updateMemoryRecord(
    int id, {
    String? content,
    int? importance,
  }) async {
    final res = await patch('/memory/records/$id', {
      if (content != null) 'content': content,
      if (importance != null) 'importance': importance,
    });
    return res.statusCode == 200;
  }

  Future<Map<String, dynamic>?> getMemoryGraph() async {
    final res = await get('/memory/graph');
    if (res.statusCode != 200) return null;
    final dynamic data = decodeJson(res);
    return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
  }

  Future<Map<String, dynamic>?> getMemoryProfile() async {
    final res = await get('/memory/profile');
    if (res.statusCode != 200) return null;
    final dynamic data = decodeJson(res);
    return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
  }

  // -- Other business objects --
  Future<List<Map<String, dynamic>>> listProjects() async {
    final res = await get('/projects');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  /// Flattened notes list (tree endpoint) for workbench "recently used".
  Future<List<Map<String, dynamic>>> listNotes() async {
    final res = await get('/plugins/notes/tree');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    if (data is! List) return [];
    final out = <Map<String, dynamic>>[];
    void walk(List<dynamic> nodes) {
      for (final node in nodes) {
        if (node is! Map) continue;
        final map = node.map((k, v) => MapEntry(k.toString(), v));
        out.add(map);
        final children = map['children'];
        if (children is List) walk(children);
      }
    }

    walk(data);
    return out;
  }

  Future<Map<String, dynamic>> getWorkbenchSummary() async {
    final res = await get('/workbench/summary');
    if (res.statusCode != 200) return {};
    return _asMap(decodeJson(res));
  }

  Future<List<String>> getWorkbenchSuggestions({bool refresh = false}) async {
    final res =
        await get('/inbox/suggestions${refresh ? '?refresh=true' : ''}');
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    final list = data is Map ? data['suggestions'] : null;
    if (list is! List) return [];
    return list
        .map((e) => e.toString().trim())
        .where((e) => e.isNotEmpty)
        .toList();
  }

  Future<List<Map<String, dynamic>>> getActivitySuggestions({
    int limit = 6,
  }) async {
    final res = await get('/insights/suggestions?limit=$limit');
    if (res.statusCode != 200) return [];
    return _asMapList(decodeJson(res)['items']);
  }

  Future<bool> acceptActivitySuggestion(int id) async {
    final res = await post('/insights/suggestions/$id/accept', const {});
    return res.statusCode == 200;
  }

  Future<bool> dismissActivitySuggestion(int id) async {
    final res = await post('/insights/suggestions/$id/dismiss', const {});
    return res.statusCode == 200;
  }

  Future<bool> executeActivitySuggestion(int id) async {
    final res = await post('/insights/suggestions/$id/execute', const {});
    return res.statusCode == 200;
  }

  // -- Agent tasks --
  Future<List<Map<String, dynamic>>> listAgentTasks({int limit = 50}) async {
    final res = await get('/agent/tasks?limit=$limit');
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<Map<String, dynamic>> createAgentTask(
    String goal, {
    int? botId,
  }) async {
    final res = await post('/agent/tasks', {
      'goal': goal,
      if (botId != null) 'bot_id': botId,
    });
    if (res.statusCode != 200 && res.statusCode != 202) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> getAgentTask(int id) async {
    final res = await get('/agent/tasks/$id');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<void> cancelAgentTask(int id) async {
    final res = await post('/agent/tasks/$id/cancel', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<Map<String, dynamic>> getAgentTaskDetail(int id) async {
    final res = await get('/runs/$id');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Stream<Map<String, dynamic>> streamAgentRun(int id) async* {
    final request =
        http.Request('GET', Uri.parse('$_baseUrl/api/runs/$id/stream'));
    final response = await _http.send(request, timeout: const Duration(seconds: 30));
    if (response.statusCode != 200) {
      final body = await response.stream.bytesToString();
      throw Exception(body.isEmpty ? '运行流连接失败' : body);
    }
    final lines = response.stream
        .timeout(const Duration(seconds: 120))
        .transform(utf8.decoder)
        .transform(const LineSplitter());
    await for (final line in lines) {
      final text = line.trim();
      if (!text.startsWith('data: ')) continue;
      final payload = text.substring(6).trim();
      if (payload.isEmpty) continue;
      try {
        final decoded = jsonDecode(payload);
        if (decoded is Map) {
          yield decoded.map((k, v) => MapEntry(k.toString(), v));
        }
      } catch (_) {
        // Ignore malformed SSE frames.
      }
    }
  }

  Future<List<Map<String, dynamic>>> pendingApprovals() async {
    final res = await get('/approvals?status=pending');
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<void> decideApproval(
    int id, {
    required bool approved,
    bool remember = false,
    String? reason,
  }) async {
    final res = await post('/approvals/$id/decision', {
      'approved': approved,
      'remember': remember,
      if (reason != null) 'reason': reason,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<Map<String, dynamic>> buildContext(String query) async {
    final res =
        await get('/context/build?q=${Uri.encodeQueryComponent(query)}');
    if (res.statusCode != 200) return {};
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> listSourceItems({int limit = 30}) async {
    final res = await get('/sources/items?page_size=$limit');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    final list = data is Map ? (data['items'] as List? ?? const []) : const [];
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<List<Map<String, dynamic>>> listMcpServers() async {
    final res = await get('/mcp/servers');
    if (res.statusCode != 200) return [];
    final dynamic data = decodeJson(res);
    final list = data is Map
        ? ((data['servers'] ?? data['items']) as List? ?? const [])
        : (data is List ? data : const []);
    return list
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<Map<String, dynamic>?> getMe() async {
    final res = await get('/auth/me');
    if (res.statusCode != 200) return null;
    final dynamic data = decodeJson(res);
    return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
  }

  Future<Map<String, dynamic>?> getProfile() async {
    final res = await get('/auth/profile');
    if (res.statusCode != 200) return null;
    final dynamic data = decodeJson(res);
    return data is Map ? data.map((k, v) => MapEntry(k.toString(), v)) : null;
  }

  Future<void> updateProfile(Map<String, dynamic> data) async {
    final res = await put('/auth/profile', data);
    if (res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
  }

  // -- SmartAssistant device (ESP32) --

  Future<Map<String, dynamic>> deviceFirmware() async {
    final res = await get('/device/firmware/latest');
    if (res.statusCode != 200) return {};
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> deviceGestures() async {
    final res = await get('/device/gestures');
    if (res.statusCode != 200) return {};
    return _asMap(decodeJson(res));
  }

  Future<void> pushToDevice({
    required String title,
    String body = '',
    String kind = 'notification',
  }) async {
    final res = await post('/device/push', {
      'title': title,
      'body': body,
      'kind': kind,
    });
    if (res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
  }

  // -- Cross-device appearance settings --
  Future<Map<String, dynamic>> getAppearanceSettings() async {
    final res = await get('/sync/settings/appearance');
    if (res.statusCode != 200) return {};
    final dynamic data = decodeJson(res);
    final list = data is Map ? (data['items'] as List? ?? const []) : const [];
    final result = <String, dynamic>{};
    for (final item in list.whereType<Map>()) {
      result[(item['key'] ?? '').toString()] = item['value'];
    }
    return result;
  }

  Future<void> pushAppearanceSetting(String key, Object? value) async {
    try {
      await put('/sync/settings/appearance/$key', {
        'value': value,
        'device_id': 'mobile',
      });
    } catch (_) {
      // Cross-device sync is best-effort; local settings remain authoritative.
    }
  }

  // -- Helpers for JSON maps/lists --
  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map) {
      return data.map((k, v) => MapEntry(k.toString(), v));
    }
    return {};
  }

  List<Map<String, dynamic>> _asMapList(dynamic data) {
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  // -- File actions --
  Future<FileItem> renameFile(int fileId, String newName) async {
    final res = await put('/files/$fileId/rename', {'new_name': newName});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return FileItem.fromJson(_asMap(decodeJson(res)));
  }

  Future<FileItem> moveFile(int fileId, String newFolderPath) async {
    final res =
        await put('/files/$fileId/move', {'new_folder_path': newFolderPath});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return FileItem.fromJson(_asMap(decodeJson(res)));
  }

  Future<FileItem> toggleFavoriteFile(int fileId) async {
    final res = await post('/files/$fileId/favorite', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return FileItem.fromJson(_asMap(decodeJson(res)));
  }

  Future<FileItem> updateFileTags(int fileId, List<String> tags) async {
    final res = await put('/files/$fileId/tags', {'tags': tags});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return FileItem.fromJson(_asMap(decodeJson(res)));
  }

  Future<void> deleteFile(int fileId) async {
    final res = await delete('/files/$fileId');
    if (res.statusCode != 200 && res.statusCode != 204) {
      throw Exception(_extractError(res));
    }
  }

  String fileStreamUrl(int fileId) =>
      '$_baseUrl/api/files/$fileId/stream?token=${Uri.encodeComponent(_token ?? '')}';

  // -- Project runs --
  Future<List<Map<String, dynamic>>> listProjectRuns(
    int projectId, {
    int limit = 50,
  }) async {
    final res = await get('/projects/$projectId/runs?limit=$limit');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> startProjectRun(
    int projectId,
    String instruction, {
    String? branch,
  }) async {
    final res = await post('/projects/$projectId/runs', {
      'instruction': instruction,
      if (branch != null && branch.isNotEmpty) 'branch': branch,
    });
    if (res.statusCode != 202 && res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  // -- Automation routines --
  Future<Map<String, dynamic>> automationOverview() async {
    final res = await get('/automation/overview');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> automationTemplates() async {
    final res = await get('/automation/templates');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    final data = _asMap(decodeJson(res));
    return _asMapList(data['templates']);
  }

  Future<List<Map<String, dynamic>>> listBots() async {
    final res = await get('/bots');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> createBot(Map<String, dynamic> data) async {
    final res = await post('/bots', data);
    if (res.statusCode != 200 && res.statusCode != 201) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> updateBot(
    int botId,
    Map<String, dynamic> data,
  ) async {
    final res = await patch('/bots/$botId', data);
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<void> deleteBot(int botId) async {
    final res = await delete('/bots/$botId');
    if (res.statusCode != 200 && res.statusCode != 204) {
      throw Exception(_extractError(res));
    }
  }

  Future<List<Map<String, dynamic>>> listBotRoutines(int botId) async {
    final res = await get('/bots/$botId/routines');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> parseAutomationRule(String text) async {
    final res = await post('/automation/parse', {'text': text});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(_asMap(decodeJson(res))['draft']);
  }

  Future<Map<String, dynamic>> createAutomationFromTemplate(
    int botId,
    String templateKey, {
    Map<String, dynamic>? overrides,
  }) async {
    final res = await post('/automation/from-template', {
      'bot_id': botId,
      'template_key': templateKey,
      if (overrides != null) 'overrides': overrides,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> createAutomationRoutine(
    int botId,
    Map<String, dynamic> data,
  ) async {
    final res = await post('/bots/$botId/routines', data);
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> automationRoutine(int routineId) async {
    final res = await get('/automation/routines/$routineId');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> dryRunAutomationRoutine(int routineId) async {
    final res = await post('/automation/routines/$routineId/dry-run', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> automationRuns(
    int routineId, {
    int limit = 20,
  }) async {
    final res = await get('/automation/routines/$routineId/runs?limit=$limit');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> automationStats(
    int routineId, {
    int days = 30,
  }) async {
    final res = await get('/automation/routines/$routineId/stats?days=$days');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> updateAutomationRoutine(
    int botId,
    int routineId,
    Map<String, dynamic> data,
  ) async {
    final res = await patch('/bots/$botId/routines/$routineId', data);
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<void> deleteAutomationRoutine(int botId, int routineId) async {
    final res = await delete('/bots/$botId/routines/$routineId');
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<Map<String, dynamic>> runAutomationRoutineNow(
    int botId,
    int routineId,
  ) async {
    final res = await post('/bots/$botId/routines/$routineId/run', const {});
    if (res.statusCode != 202 && res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  // -- Daily insights --
  Future<List<Map<String, dynamic>>> dailyInsights({int days = 7}) async {
    final res = await get('/insights/daily?days=$days');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  /// Stored weekly reviews (one row per week).
  Future<List<Map<String, dynamic>>> weeklyReviews({int limit = 8}) async {
    final res = await get('/insights/weekly?limit=$limit');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> runDailyInsight({String? day}) async {
    final res = await post('/insights/daily/run', {
      'force': true,
      if (day != null) 'day': day,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  // -- Notes knowledge base (RAG) --
  Future<Map<String, dynamic>> askNotes(String question, {int? topK}) async {
    final res = await post('/plugins/notes/rag/ask', {
      'question': question,
      if (topK != null) 'top_k': topK,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> searchNotesRag(String query, {int? topK}) async {
    final res = await post('/plugins/notes/rag/search', {
      'q': query,
      if (topK != null) 'top_k': topK,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> noteVersions(int noteId) async {
    final res = await get('/plugins/notes/$noteId/versions');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(_asMap(decodeJson(res))['versions']);
  }

  Future<Map<String, dynamic>> noteVersion(int noteId, int versionId) async {
    final res = await get('/plugins/notes/$noteId/versions/$versionId');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> restoreNoteVersion(
    int noteId,
    int versionId,
  ) async {
    final res = await post(
        '/plugins/notes/$noteId/versions/$versionId/restore', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> similarNotes(
    int noteId, {
    int limit = 5,
  }) async {
    final res = await get('/plugins/notes/$noteId/similar?limit=$limit');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(_asMap(decodeJson(res))['results']);
  }

  Future<List<Map<String, dynamic>>> searchNotes(String query) async {
    final res = await get(
      '/plugins/notes/search?q=${Uri.encodeQueryComponent(query)}',
    );
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> importNoteFromUrl(
    String url, {
    int? parentId,
    String? title,
  }) async {
    final res = await post('/plugins/notes/import/url', {
      'url': url,
      if (parentId != null) 'parent_id': parentId,
      if (title != null && title.isNotEmpty) 'title': title,
    });
    if (res.statusCode != 201 && res.statusCode != 200) {
      throw Exception(_extractError(res));
    }
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> backfillInsights({int days = 7}) async {
    final res = await post('/insights/daily/backfill?days=$days', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res));
  }

  Future<Map<String, dynamic>> dingtalkStatus() async {
    final res = await get('/plugins/dingtalk/status');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> startDingtalkLogin() async {
    final res = await post('/plugins/dingtalk/login/start', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> dingtalkLoginStatus() async {
    final res = await get('/plugins/dingtalk/login/status');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<void> dingtalkLogout() async {
    final res = await post('/plugins/dingtalk/logout', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<List<Map<String, dynamic>>> dingtalkConversations() async {
    final res = await get('/plugins/dingtalk/conversations');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res)['items']);
  }

  Future<List<Map<String, dynamic>>> dingtalkMessages(
    String conversationId, {
    int limit = 100,
  }) async {
    final res = await get(
      '/plugins/dingtalk/messages?conversation_id=${Uri.encodeQueryComponent(conversationId)}&limit=$limit',
    );
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMapList(decodeJson(res)['items']);
  }


  // -- Quick capture --
  Future<Map<String, dynamic>> createCapture({
    required String kind,
    String? url,
    String? text,
    String? title,
    String source = 'mobile',
  }) async {
    final res = await _http.post(
      Uri.parse('$_baseUrl/api/captures'),
      headers: _headers,
      body: jsonEncode({
        'kind': kind,
        'source': source,
        if (url != null) 'url': url,
        if (text != null) 'text': text,
        if (title != null) 'title': title,
      }),
    );
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<Map<String, dynamic>> uploadCapture(
    List<int> bytes,
    String filename, {
    String? text,
    String? title,
    String? mimeType,
    String source = 'mobile',
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$_baseUrl/api/captures/upload'),
    );
    if (_token != null) {
      request.headers['Authorization'] = 'Bearer $_token';
    }
    request.fields['text'] = text ?? '';
    request.fields['title'] = title ?? '';
    request.fields['source'] = source;
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: filename,
      contentType: mimeType == null ? null : MediaType.parse(mimeType),
    ));
    final streamed = await request.send();
    final res = await http.Response.fromStream(streamed);
    if (res.statusCode != 200) throw Exception(_extractError(res));
    return _asMap(decodeJson(res));
  }

  Future<List<Map<String, dynamic>>> listCaptures({int limit = 50}) async {
    final res = await get('/captures?limit=$limit');
    if (res.statusCode != 200) throw Exception(_extractError(res));
    final data = _asMap(decodeJson(res));
    return _asMapList(data['items']);
  }

  Future<void> convertCapture(int id, String target, {Map<String, dynamic>? params}) async {
    final res = await post('/captures/$id/convert', {
      'target': target,
      if (params != null) 'params': params,
    });
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }

  Future<void> analyzeCapture(int id) async {
    final res = await post('/captures/$id/analyze', const {});
    if (res.statusCode != 200) throw Exception(_extractError(res));
  }
}
