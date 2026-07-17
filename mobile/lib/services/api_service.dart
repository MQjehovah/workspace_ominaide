import 'dart:convert';
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
      Uri.parse('$serverUrl/api/v1/auth/login'),
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

  Future<List<FileItem>> listFiles({String folderPath = '/'}) async {
    final res = await http.get(
      Uri.parse('$_baseUrl/api/v1/files?page_size=100&folder_path=${Uri.encodeComponent(folderPath)}'),
      headers: _headers,
    );
    if (res.statusCode != 200) return [];
    final data = jsonDecode(res.body);
    return (data['files'] as List).map((f) => FileItem.fromJson(f)).toList();
  }

  Future<Map<String, dynamic>> getUploadUrl(String filename, String folderPath) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/v1/files/upload-url'),
      headers: _headers,
      body: jsonEncode({'filename': filename, 'folder_path': folderPath}),
    );
    if (res.statusCode != 200) throw Exception('Failed to get upload URL');
    return jsonDecode(res.body);
  }

  Future<void> confirmUpload(int fileId) async {
    await http.post(
      Uri.parse('$_baseUrl/api/v1/files/confirm'),
      headers: _headers,
      body: jsonEncode({'file_id': fileId}),
    );
  }

  Future<String> getDownloadUrl(int fileId) async {
    final res = await http.get(
      Uri.parse('$_baseUrl/api/v1/files/$fileId/download-url'),
      headers: _headers,
    );
    if (res.statusCode != 200) throw Exception('Failed to get download URL');
    final data = jsonDecode(res.body);
    return data['download_url'];
  }

  Future<FileItem> createFolder(String name, String parentPath) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/v1/files/folder'),
      headers: _headers,
      body: jsonEncode({'name': name, 'parent_path': parentPath}),
    );
    if (res.statusCode != 201) throw Exception('Failed to create folder');
    return FileItem.fromJson(jsonDecode(res.body));
  }

  Future<http.Response> get(String path) async {
    final prefix = path.startsWith('/plugins/') ? '/api' : '/api/v1';
    return await http.get(Uri.parse('$_baseUrl$prefix$path'), headers: _headers);
  }

  Future<http.Response> post(String path, Map<String, dynamic> body) async {
    final prefix = path.startsWith('/plugins/') ? '/api' : '/api/v1';
    return await http.post(Uri.parse('$_baseUrl$prefix$path'), headers: _headers, body: jsonEncode(body));
  }

  Future<http.Response> put(String path, Map<String, dynamic> body) async {
    final prefix = path.startsWith('/plugins/') ? '/api' : '/api/v1';
    return await http.put(Uri.parse('$_baseUrl$prefix$path'), headers: _headers, body: jsonEncode(body));
  }

  Future<http.Response> delete(String path) async {
    final prefix = path.startsWith('/plugins/') ? '/api' : '/api/v1';
    return await http.delete(Uri.parse('$_baseUrl$prefix$path'), headers: _headers);
  }

  Future<String> callMCP(String toolName, Map<String, dynamic> args) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/v1/mcp/call'),
      headers: _headers,
      body: jsonEncode({'name': toolName, 'arguments': args}),
    );
    if (res.statusCode != 200) return 'Error: ${res.statusCode}';
    final data = jsonDecode(res.body);
    return data['content']?[0]?['text'] ?? 'No response';
  }
}
