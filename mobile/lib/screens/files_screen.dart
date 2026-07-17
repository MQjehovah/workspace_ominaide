import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';
import '../models/file_item.dart';

class FilesScreen extends StatefulWidget {
  const FilesScreen({super.key});
  @override
  State<FilesScreen> createState() => _FilesScreenState();
}

class _FilesScreenState extends State<FilesScreen> {
  String _currentPath = '/';
  List<FileItem> _files = [];
  bool _loading = true;
  final _history = <String>['/'];

  @override
  void initState() {
    super.initState();
    _loadFiles();
  }

  Future<void> _loadFiles() async {
    setState(() => _loading = true);
    final files = await ApiService().listFiles(folderPath: _currentPath);
    if (!mounted) return;
    setState(() { _files = files; _loading = false; });
  }

  void _openFolder(FileItem folder) {
    final path = '${folder.folderPath.replaceAll(RegExp(r'/+$'), '')}/${folder.originalName}/';
    _history.add(_currentPath);
    setState(() { _currentPath = path; });
    _loadFiles();
  }

  void _goBack() {
    if (_history.isEmpty) return;
    setState(() => _currentPath = _history.removeLast());
    _loadFiles();
  }

  void _goRoot() {
    _history.clear();
    setState(() => _currentPath = '/');
    _loadFiles();
  }

  Future<void> _createFolder() async {
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final c = TextEditingController();
        return AlertDialog(
          title: const Text('新建文件夹'),
          content: TextField(controller: c, decoration: const InputDecoration(hintText: '文件夹名称'), autofocus: true),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            TextButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('创建')),
          ],
        );
      },
    );
    if (name == null || name.isEmpty) return;
    try {
      await ApiService().createFolder(name, _currentPath);
      _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _uploadFile() async {
    final result = await FilePicker.platform.pickFiles();
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null) return;
    try {
      final uploadData = await ApiService().getUploadUrl(file.name, _currentPath);
      final uploadUrl = uploadData['upload_url'] as String;
      final fileId = uploadData['file_id'] as int;
      final localFile = File(file.path!);
      final http = await HttpClient().putUrl(Uri.parse(uploadUrl));
      http.headers.contentType = ContentType('application', 'octet-stream');
      http.contentLength = await localFile.length();
      await localFile.openRead().pipe(http);
      final response = await http.close();
      if (response.statusCode == 200) {
        await ApiService().confirmUpload(fileId);
        _loadFiles();
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('上传失败: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final crumbs = _currentPath.split('/').where((s) => s.isNotEmpty).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('文件'),
        actions: [
          IconButton(icon: const Icon(Icons.create_new_folder_outlined), onPressed: _createFolder, tooltip: '新建文件夹'),
          IconButton(icon: const Icon(Icons.upload_file), onPressed: _uploadFile, tooltip: '上传'),
        ],
      ),
      body: Column(
        children: [
          // Breadcrumb
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(children: [
              GestureDetector(onTap: _goRoot, child: const Icon(Icons.home, size: 18)),
              if (_history.isNotEmpty)
                GestureDetector(onTap: _goBack, child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 8), child: Icon(Icons.arrow_back_ios, size: 14),
                )),
              ...crumbs.asMap().entries.map((e) {
                final path = '/' + crumbs.sublist(0, e.key + 1).join('/');
                return GestureDetector(
                  onTap: () {
                    _history.add(_currentPath);
                    setState(() => _currentPath = '$path/');
                    _loadFiles();
                  },
                  child: Text('/ ${e.value}', style: TextStyle(fontSize: 12, color: e.key == crumbs.length - 1 ? Colors.black : Colors.blue)),
                );
              }),
            ]),
          ),
          const Divider(height: 1),
          // Files
          Expanded(
            child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _files.isEmpty
                ? const Center(child: Text('空文件夹', style: TextStyle(color: Colors.grey)))
                : RefreshIndicator(
                    onRefresh: _loadFiles,
                    child: ListView.builder(
                      itemCount: _files.length,
                      itemBuilder: (_, i) {
                        final f = _files[i];
                        final ext = f.originalName.split('.').last.toLowerCase();
                        final isImg = ['jpg', 'jpeg', 'png', 'gif', 'webp'].contains(ext);
                        return ListTile(
                          leading: Icon(
                            f.isFolder ? Icons.folder :
                            isImg ? Icons.image :
                            Icons.insert_drive_file,
                            color: f.isFolder ? Colors.amber : isImg ? Colors.green : Colors.blue,
                            size: 32,
                          ),
                          title: Text(f.originalName, style: const TextStyle(fontSize: 14)),
                          subtitle: Text(f.isFolder ? '文件夹' : '${f.sizeFormatted}  ${f.createdAt.isNotEmpty ? f.createdAt.substring(0, 10) : ''}',
                            style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                          onTap: f.isFolder ? () => _openFolder(f) : null,
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
