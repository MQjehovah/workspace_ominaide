import 'dart:io';
import 'dart:typed_data';
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
      // Try presigned URL first
      final uploadData = await ApiService().getUploadUrl(file.name, _currentPath);
      final uploadUrl = uploadData['upload_url'] as String?;
      final fileId = uploadData['file_id'] as int?;

      if (uploadUrl != null && uploadUrl.isNotEmpty) {
        final localFile = File(file.path!);
        final httpClient = HttpClient();
        final request = await httpClient.putUrl(Uri.parse(uploadUrl));
        request.headers.contentType = ContentType('application', 'octet-stream');
        request.contentLength = await localFile.length();
        await localFile.openRead().pipe(request);
        final response = await request.close();
        if (response.statusCode == 200 && fileId != null) {
          await ApiService().confirmUpload(fileId);
        }
      } else {
        // Proxy upload
        await ApiService().uploadFileDirect(file.path!, file.name, _currentPath);
      }
      _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('上传失败: $e')));
    }
  }

  // Download and save file
  Future<void> _downloadFile(FileItem f) async {
    try {
      // Show file preview for images, download for others
      final ext = f.originalName.split('.').last.toLowerCase();
      final isImg = ['jpg', 'jpeg', 'png', 'gif', 'webp'].contains(ext);

      if (isImg) {
        // Download and show preview
        final bytes = await ApiService().downloadFile(f.id);
        if (!mounted) return;
        if (mounted) {
          await showDialog(
            context: context,
            builder: (_) => Dialog(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AppBar(title: Text(f.originalName, style: const TextStyle(fontSize: 14)), automaticallyImplyLeading: false),
                  Expanded(child: InteractiveViewer(child: Image.memory(Uint8List.fromList(bytes), fit: BoxFit.contain))),
                ],
              ),
            ),
          );
        }
      } else {
        // Download and save
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('正在下载...')));
        final path = await ApiService().saveFileLocally(f.id, f.originalName);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('已下载到: $path')));
        // Try to open file
        if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].contains(ext)) {
          await Process.run('cmd', ['/c', 'start', '', path], runInShell: true);
        }
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('下载失败: $e')));
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
          // Files list
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
                          onTap: f.isFolder ? () => _openFolder(f) : () => _downloadFile(f),
                          trailing: f.isFolder ? null : const Icon(Icons.download, size: 18),
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
