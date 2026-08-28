import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/file_item.dart';
import 'chat_stream_stub.dart'
    if (dart.library.html) 'chat_stream_web.dart'
    if (dart.library.io) 'chat_stream_io.dart';
import 'file_save_stub.dart'
    if (dart.library.html) 'file_save_web.dart'
    if (dart.library.io) 'file_save_io.dart';

class ApiService {
  String _baseUrl = 'http://mqgeek.com:8000';
  String? _token;

  static final ApiService _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._();

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  Map<String, String> get _authHeaders => {
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('token');
    _baseUrl = prefs.getString('serverUrl') ?? 'http://mqgeek.com:8000';
  }

  Future<void> saveAuth(String token, String serverUrl) async {
    _token = token;
    _baseUrl = serverUrl;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('token', token);
    await prefs.setString('serverUrl', serverUrl);
  }

  Future<void> logout() async {
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('token');
    await prefs.remove('serverUrl');
  }

  bool get isLoggedIn => _token != null;

  Future<String> login(String serverUrl, String username, String password) async {
    final res = await http.post(
      Uri.parse('$serverUrl/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );
    if (res.statusCode != 200) {
      final detail = decodeJson(res);
      throw Exception(detail['detail'] ?? 'Login failed');
    }
    final data = decodeJson(res);
    await saveAuth(data['access_token'], serverUrl);
    return data['access_token'];
  }

  // -- Files --
  Future<List<FileItem>> listFiles({String folderPath = '/'}) async {
    final res = await http.get(
      Uri.parse('$_baseUrl/api/files?page_size=100&folder_path=${Uri.encodeComponent(folderPath)}'),
      headers: _headers,
    );
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    return (data['files'] as List).map((f) => FileItem.fromJson(f)).toList();
  }

  // -- Vibecoding --
  Future<List<dynamic>> listVibecodingTasks({int limit = 50}) async {
    try {
      final res = await http.get(
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

  Future<List<dynamic>> listVibecodingDevices() async {
    try {
      final res = await http.get(
        Uri.parse('$_baseUrl/api/vibecoding/devices'),
        headers: _authHeaders,
      );
      if (res.statusCode != 200) return [];
      final data = decodeJson(res);
      return (data['devices'] as List?) ?? [];
    } catch (_) {
      return [];
    }
  }

  /// Download file bytes through backend proxy (or presigned URL).
  Future<List<int>> downloadFile(int fileId) async {
    final dlRes = await http.get(
      Uri.parse('$_baseUrl/api/files/$fileId/download-url'),
      headers: _headers,
    );
    if (dlRes.statusCode != 200) throw Exception('Failed to get download info');
    final dlData = decodeJson(dlRes);
    final dlUrl = dlData['download_url'] as String?;

    if (dlUrl != null && dlUrl.isNotEmpty) {
      final res = await http.get(Uri.parse(dlUrl));
      if (res.statusCode != 200) throw Exception('Download failed: ${res.statusCode}');
      return res.bodyBytes;
    } else {
      final res = await http.get(
        Uri.parse('$_baseUrl/api/files/$fileId/download'),
        headers: _authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Download failed: ${res.statusCode}');
      return res.bodyBytes;
    }
  }

  /// Save downloaded bytes to local file, returns the file path.
  Future<String> saveFileLocally(int fileId, String filename) async {
    final bytes = await downloadFile(fileId);
    final out = await writeBytesLocal(filename, bytes);
    return out;
  }

  /// Upload file directly through backend proxy.
  Future<void> uploadFileDirect(String filePath, String filename, String folderPath) async {
    final uri = Uri.parse('$_baseUrl/api/files/upload/direct?folder_path=${Uri.encodeComponent(folderPath)}');
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_authHeaders)
      ..files.add(await http.MultipartFile.fromPath('file', filePath, filename: filename));
    final streamed = await request.send();
    if (streamed.statusCode != 200) throw Exception('Upload failed: ${streamed.statusCode}');
  }

  Future<Map<String, dynamic>> getUploadUrl(String filename, String folderPath) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/files/upload-url'),
      headers: _headers,
      body: jsonEncode({'filename': filename, 'folder_path': folderPath}),
    );
    if (res.statusCode != 200) throw Exception('Failed to get upload URL');
    return decodeJson(res);
  }

  Future<void> confirmUpload(int fileId) async {
    await http.post(
      Uri.parse('$_baseUrl/api/files/confirm'),
      headers: _headers,
      body: jsonEncode({'file_id': fileId}),
    );
  }

  Future<FileItem> createFolder(String name, String parentPath) async {
    final res = await http.post(
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

  void _extractText(List nodes, StringBuffer buffer) {
    for (final node in nodes) {
      if (node is! Map) continue;
      if (node['type'] == 'text' && node['text'] is String) {
        buffer.write(node['text']);
      }
      if (node['type'] == 'paragraph') {
        if (buffer.isNotEmpty && !buffer.toString().endsWith('\n')) buffer.writeln();
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
            if (row is Map && row['type'] == 'tableRow' && row['content'] is List) {
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
    return await http.get(Uri.parse('$_baseUrl/api$path'), headers: _headers);
  }

  Future<http.Response> post(String path, Map<String, dynamic> body) async {
    return await http.post(Uri.parse('$_baseUrl/api$path'), headers: _headers, body: jsonEncode(body));
  }

  Future<http.Response> put(String path, Map<String, dynamic> body) async {
    return await http.put(Uri.parse('$_baseUrl/api$path'), headers: _headers, body: jsonEncode(body));
  }

  Future<http.Response> delete(String path) async {
    return await http.delete(Uri.parse('$_baseUrl/api$path'), headers: _headers);
  }

  // -- Chat --
  Future<String> chat(String message, {List<Map<String, String>>? history, bool agent = false}) async {
    final path = agent ? '/api/chat/agent' : '/api/chat';
    final res = await http.post(
      Uri.parse('$_baseUrl$path'),
      headers: _headers,
      body: jsonEncode({'message': message, 'history': history ?? []}),
    );
    if (res.statusCode != 200) {
      final detail = _extractError(res);
      throw Exception(detail);
    }
    final data = decodeJson(res);
    return (data['reply'] as String?) ?? '';
  }

  /// Stream chat via SSE (incremental on all platforms).
  Stream<String> chatStream(String message, {List<Map<String, String>>? history}) {
    final path = '/api/chat/stream';
    final uri = Uri.parse('$_baseUrl$path');
    final headers = <String, String>{..._headers};
    final body = jsonEncode({'message': message, 'history': history ?? []});
    return streamChatSse(uri, headers, body);
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
  Future<List<Map<String, dynamic>>> listScheduleEvents({String? start, String? end}) async {    final q = <String, String>{};
    if (start != null) q['start'] = start;
    if (end != null) q['end'] = end;
    final uri = Uri.parse('$_baseUrl/api/schedule').replace(queryParameters: q.isEmpty ? null : q);
    final res = await http.get(uri, headers: _headers);
    if (res.statusCode != 200) return [];
    final d = decodeJson(res);
    return (d as List? ?? []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createScheduleEvent(Map<String, dynamic> data) async {
    final res = await http.post(Uri.parse('$_baseUrl/api/schedule'), headers: _headers, body: jsonEncode(data));
    if (res.statusCode != 201 && res.statusCode != 200) throw Exception(_extractError(res));
    return decodeJson(res);
  }

  Future<void> deleteScheduleEvent(int id) async {
    await http.delete(Uri.parse('$_baseUrl/api/schedule/$id'), headers: _headers);
  }

  // -- Todo --
  Future<List<Map<String, dynamic>>> listTodoItems() async {
    final res = await http.get(Uri.parse('$_baseUrl/api/plugins/todo/items'), headers: _headers);
    if (res.statusCode != 200) return [];
    final d = decodeJson(res);
    final list = d['items'] as List? ?? d as List? ?? [];
    return list.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createTodoItem(Map<String, dynamic> data) async {
    final res = await http.post(Uri.parse('$_baseUrl/api/plugins/todo/items'), headers: _headers, body: jsonEncode(data));
    if (res.statusCode != 201 && res.statusCode != 200) throw Exception(_extractError(res));
    return decodeJson(res);
  }

  Future<void> updateTodoItem(int id, Map<String, dynamic> data) async {
    await http.put(Uri.parse('$_baseUrl/api/plugins/todo/items/$id'), headers: _headers, body: jsonEncode(data));
  }

  Future<void> deleteTodoItem(int id) async {
    await http.delete(Uri.parse('$_baseUrl/api/plugins/todo/items/$id'), headers: _headers);
  }

  // -- Notifications --
  Future<List<Map<String, dynamic>>> listNotifications({int limit = 20}) async {
    final res = await http.get(Uri.parse('$_baseUrl/api/notifications?limit=$limit'), headers: _headers);
    if (res.statusCode != 200) return [];
    final d = decodeJson(res);
    return (d['notifications'] as List? ?? []).cast<Map<String, dynamic>>();
  }

  Future<void> markNotificationsRead() async {
    await http.put(Uri.parse('$_baseUrl/api/notifications/read-all'), headers: _headers, body: '{}');
  }

  // -- MCP --
  Future<String> callMCP(String toolName, Map<String, dynamic> args) async {
    final res = await http.post(
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
      'articles': <Map<String, dynamic>>[],
      'semantic': <Map<String, dynamic>>[],
    };
    try {
      final filesRes = await http.get(
        Uri.parse('$_baseUrl/api/files?search=${Uri.encodeComponent(query)}&page_size=10'),
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
      final rssRes = await http.get(
        Uri.parse('$_baseUrl/api/rss/search?q=${Uri.encodeComponent(query)}&page_size=10'),
        headers: _headers,
      );
      if (rssRes.statusCode == 200) {
        final data = decodeJson(rssRes);
        result['articles'] = (data['items'] as List? ?? []).cast<Map<String, dynamic>>();
      }
    } catch (_) {}
    try {
      final semRes = await http.post(
        Uri.parse('$_baseUrl/api/search'),
        headers: _headers,
        body: jsonEncode({'q': query, 'top_k': 5}),
      );
      if (semRes.statusCode == 200) {
        final data = decodeJson(semRes);
        result['semantic'] = (data['results'] as List? ?? []).cast<Map<String, dynamic>>();
      }
    } catch (_) {}
    return result;
  }

  // -- Audio --
  Future<List<FileItem>> listAudioFiles() async {
    final res = await http.get(
      Uri.parse('$_baseUrl/api/files?page_size=200'),
      headers: _headers,
    );
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    final audioMimes = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/flac', 'audio/ogg', 'audio/aac', 'audio/wma', 'audio/x-m4a'];
    final audioExts = ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma'];
    return (data['files'] as List)
      .map((f) => FileItem.fromJson(f))
      .where((f) => !f.isFolder && (
        audioMimes.contains(f.mimeType) ||
        audioExts.contains(f.originalName.split('.').last.toLowerCase())
      ))
      .toList();
  }

  // -- Playlists --
  Future<List<Map<String, dynamic>>> listPlaylists() async {
    final res = await http.get(Uri.parse('$_baseUrl/api/music/playlists'), headers: _headers);
    if (res.statusCode != 200) return [];
    return ((decodeJson(res)['playlists'] as List?) ?? []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createPlaylist(String name) async {
    final res = await http.post(Uri.parse('$_baseUrl/api/music/playlists'),
      headers: _headers, body: jsonEncode({'name': name}));
    if (res.statusCode != 201) throw Exception('Failed to create playlist');
    return decodeJson(res);
  }

  Future<void> deletePlaylist(int id) async {
    await http.delete(Uri.parse('$_baseUrl/api/music/playlists/$id'), headers: _headers);
  }

  Future<List<Map<String, dynamic>>> listPlaylistSongs(int playlistId) async {
    final res = await http.get(Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs'), headers: _headers);
    if (res.statusCode != 200) return [];
    final data = decodeJson(res);
    return (data['songs'] as List?)?.cast<Map<String, dynamic>>() ?? [];
  }

  Future<void> addSongToPlaylist(int playlistId, int fileId) async {
    final res = await http.post(Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs'),
      headers: _headers, body: jsonEncode({'file_id': fileId}));
    if (res.statusCode != 201) throw Exception('Failed to add song');
  }

  Future<void> removeSongFromPlaylist(int playlistId, int itemId) async {
    await http.delete(Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs/$itemId'), headers: _headers);
  }
}
