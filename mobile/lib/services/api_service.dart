import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/file_item.dart';

class ApiService {
  String _baseUrl = 'http://10.0.2.2:8000';
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
    _baseUrl = prefs.getString('serverUrl') ?? 'http://10.0.2.2:8000';
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
      final detail = jsonDecode(res.body);
      throw Exception(detail['detail'] ?? 'Login failed');
    }
    final data = jsonDecode(res.body);
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
    final data = jsonDecode(res.body);
    return (data['files'] as List).map((f) => FileItem.fromJson(f)).toList();
  }

  /// Download file bytes through backend proxy (or presigned URL).
  Future<List<int>> downloadFile(int fileId) async {
    final dlRes = await http.get(
      Uri.parse('$_baseUrl/api/files/$fileId/download-url'),
      headers: _headers,
    );
    if (dlRes.statusCode != 200) throw Exception('Failed to get download info');
    final dlData = jsonDecode(dlRes.body);
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
    final dir = Directory.systemTemp;
    final localPath = '${dir.path}/$filename';
    final bytes = await downloadFile(fileId);
    await File(localPath).writeAsBytes(bytes);
    return localPath;
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
    return jsonDecode(res.body);
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
    return FileItem.fromJson(jsonDecode(res.body));
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

  // -- MCP --
  Future<String> callMCP(String toolName, Map<String, dynamic> args) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/mcp/call'),
      headers: _headers,
      body: jsonEncode({'name': toolName, 'arguments': args}),
    );
    if (res.statusCode != 200) return 'Error: ${res.statusCode}';
    final data = jsonDecode(res.body);
    return data['content']?[0]?['text'] ?? 'No response';
  }

  // -- Audio --
  Future<List<FileItem>> listAudioFiles() async {
    final res = await http.get(
      Uri.parse('$_baseUrl/api/files?page_size=200'),
      headers: _headers,
    );
    if (res.statusCode != 200) return [];
    final data = jsonDecode(res.body);
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
    return ((jsonDecode(res.body)['playlists'] as List?) ?? []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createPlaylist(String name) async {
    final res = await http.post(Uri.parse('$_baseUrl/api/music/playlists'),
      headers: _headers, body: jsonEncode({'name': name}));
    if (res.statusCode != 201) throw Exception('Failed to create playlist');
    return jsonDecode(res.body);
  }

  Future<void> deletePlaylist(int id) async {
    await http.delete(Uri.parse('$_baseUrl/api/music/playlists/$id'), headers: _headers);
  }

  Future<List<Map<String, dynamic>>> listPlaylistSongs(int playlistId) async {
    final res = await http.get(Uri.parse('$_baseUrl/api/music/playlists/$playlistId/songs'), headers: _headers);
    if (res.statusCode != 200) return [];
    final data = jsonDecode(res.body);
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
