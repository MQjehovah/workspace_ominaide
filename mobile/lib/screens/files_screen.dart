import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/file_item.dart';
import '../services/api_service.dart';

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
    setState(() {
      _files = files;
      _loading = false;
    });
  }

  void _openFolder(FileItem folder) {
    final path =
        '${folder.folderPath.replaceAll(RegExp(r'/+$'), '')}/${folder.originalName}/';
    _history.add(_currentPath);
    setState(() => _currentPath = path);
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
          content: TextField(
            controller: c,
            decoration: const InputDecoration(hintText: '文件夹名称'),
            autofocus: true,
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            TextButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('创建')),
          ],
        );
      },
    );
    if (name == null || name.trim().isEmpty) return;
    try {
      await ApiService().createFolder(name.trim(), _currentPath);
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
        await ApiService().uploadFileDirect(file.path!, file.name, _currentPath);
      }
      _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('上传失败: $e')));
    }
  }

  String _ext(FileItem f) => f.originalName.split('.').last.toLowerCase();

  bool _isImage(FileItem f) =>
      ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'bmp'].contains(_ext(f));

  bool _isStreamable(FileItem f) => [
        'mp4', 'mov', 'm4v', 'webm', 'mkv',
        'mp3', 'm4a', 'wav', 'aac', 'flac', 'ogg',
        'pdf',
      ].contains(_ext(f));

  Future<void> _preview(FileItem f) async {
    if (_isImage(f)) {
      try {
        final bytes = await ApiService().downloadFile(f.id);
        if (!mounted) return;
        await showDialog<void>(
          context: context,
          builder: (_) => Dialog(
            child: SizedBox(
              height: 480,
              child: Column(
                children: [
                  AppBar(
                    title: Text(f.originalName, style: const TextStyle(fontSize: 14)),
                    automaticallyImplyLeading: false,
                  ),
                  Expanded(
                    child: InteractiveViewer(
                      child: Image.memory(
                        Uint8List.fromList(bytes),
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('预览失败: $e')));
      }
      return;
    }
    if (_isStreamable(f)) {
      final ok = await launchUrl(
        Uri.parse(ApiService().fileStreamUrl(f.id)),
        mode: LaunchMode.externalApplication,
      );
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('没有可用的播放器/阅读器')),
        );
      }
      return;
    }
    await _shareFile(f);
  }

  Future<void> _shareFile(FileItem f) async {
    try {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('正在准备文件...')),
      );
      final path = await ApiService().saveFileLocally(f.id, f.originalName);
      if (!mounted) return;
      await Share.shareXFiles([XFile(path)], text: f.originalName);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('下载失败: $e')));
    }
  }

  Future<void> _toggleFavorite(FileItem f) async {
    try {
      await ApiService().toggleFavoriteFile(f.id);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('操作失败: $e')));
    }
  }

  Future<void> _rename(FileItem f) async {
    final ctl = TextEditingController(text: f.originalName);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('重命名'),
        content: TextField(controller: ctl, autofocus: true),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    ctl.dispose();
    if (name == null || name.isEmpty || name == f.originalName) return;
    try {
      await ApiService().renameFile(f.id, name);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('重命名失败: $e')));
    }
  }

  Future<void> _move(FileItem f) async {
    final ctl = TextEditingController(text: f.folderPath);
    final folder = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('移动到'),
        content: TextField(
          controller: ctl,
          autofocus: true,
          decoration: const InputDecoration(hintText: '/ 或 /文件夹/'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
            child: const Text('移动'),
          ),
        ],
      ),
    );
    ctl.dispose();
    if (folder == null || folder.isEmpty || folder == f.folderPath) return;
    try {
      var target = folder;
      if (!target.startsWith('/')) target = '/$target';
      if (!target.endsWith('/')) target = '$target/';
      await ApiService().moveFile(f.id, target);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('移动失败: $e')));
    }
  }

  Future<void> _editTags(FileItem f) async {
    final ctl = TextEditingController(text: f.tags.join(', '));
    final raw = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('标签'),
        content: TextField(
          controller: ctl,
          autofocus: true,
          decoration: const InputDecoration(hintText: '用逗号分隔，例如：工作, 重要'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, ctl.text),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    ctl.dispose();
    if (raw == null) return;
    final tags = raw
        .split(RegExp(r'[,，]'))
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    try {
      await ApiService().updateFileTags(f.id, tags);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('保存失败: $e')));
    }
  }

  Future<void> _delete(FileItem f) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除文件'),
        content: Text('确定删除「${f.originalName}」？文件会进入回收站。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().deleteFile(f.id);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('删除失败: $e')));
    }
  }

  List<PopupMenuEntry<String>> _menuItems(FileItem f) {
    return [
      if (!f.isFolder) ...[
        const PopupMenuItem(value: 'preview', child: Text('预览/打开')),
        const PopupMenuItem(value: 'share', child: Text('分享 / 存储到文件')),
        const PopupMenuItem(value: 'favorite', child: Text('收藏 / 取消收藏')),
      ],
      const PopupMenuItem(value: 'rename', child: Text('重命名')),
      const PopupMenuItem(value: 'move', child: Text('移动')),
      if (!f.isFolder) const PopupMenuItem(value: 'tags', child: Text('标签')),
      const PopupMenuItem(value: 'delete', child: Text('删除')),
    ];
  }

  Future<void> _handleMenu(String action, FileItem f) async {
    switch (action) {
      case 'preview':
        await _preview(f);
        break;
      case 'share':
        await _shareFile(f);
        break;
      case 'favorite':
        await _toggleFavorite(f);
        break;
      case 'rename':
        await _rename(f);
        break;
      case 'move':
        await _move(f);
        break;
      case 'tags':
        await _editTags(f);
        break;
      case 'delete':
        await _delete(f);
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final crumbs = _currentPath.split('/').where((s) => s.isNotEmpty).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('文件'),
        actions: [
          IconButton(
            icon: const Icon(Icons.create_new_folder_outlined),
            onPressed: _createFolder,
            tooltip: '新建文件夹',
          ),
          IconButton(
            icon: const Icon(Icons.upload_file),
            onPressed: _uploadFile,
            tooltip: '上传',
          ),
        ],
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                GestureDetector(onTap: _goRoot, child: const Icon(Icons.home, size: 18)),
                if (_history.isNotEmpty)
                  GestureDetector(
                    onTap: _goBack,
                    child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 8),
                      child: Icon(Icons.arrow_back_ios, size: 14),
                    ),
                  ),
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: crumbs.asMap().entries.map((e) {
                        final path = '/' + crumbs.sublist(0, e.key + 1).join('/');
                        return GestureDetector(
                          onTap: () {
                            _history.add(_currentPath);
                            setState(() => _currentPath = '$path/');
                            _loadFiles();
                          },
                          child: Text(
                            '/ ${e.value}',
                            style: TextStyle(
                              fontSize: 12,
                              color: e.key == crumbs.length - 1
                                  ? Theme.of(context).colorScheme.onSurface
                                  : Theme.of(context).colorScheme.primary,
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _files.isEmpty
                    ? const Center(
                        child: Text('空文件夹', style: TextStyle(color: Colors.grey)),
                      )
                    : RefreshIndicator(
                        onRefresh: _loadFiles,
                        child: ListView.builder(
                          itemCount: _files.length,
                          itemBuilder: (_, i) {
                            final f = _files[i];
                            final isImg = _isImage(f);
                            final hasTags = f.tags.isNotEmpty;
                            return ListTile(
                              leading: Icon(
                                f.isFolder
                                    ? Icons.folder
                                    : isImg
                                        ? Icons.image
                                        : Icons.insert_drive_file,
                                color: f.isFolder
                                    ? Colors.amber
                                    : isImg
                                        ? Colors.green
                                        : Colors.blue,
                                size: 32,
                              ),
                              title: Row(
                                children: [
                                  Flexible(
                                    child: Text(
                                      f.originalName,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(fontSize: 14),
                                    ),
                                  ),
                                  if (f.isFavorite) ...[
                                    const SizedBox(width: 4),
                                    const Icon(Icons.star, size: 14, color: Colors.amber),
                                  ],
                                ],
                              ),
                              subtitle: Text(
                                f.isFolder
                                    ? '文件夹'
                                    : '${f.sizeFormatted}  '
                                        '${f.createdAt.isNotEmpty ? f.createdAt.substring(0, 10) : ''}'
                                        '${hasTags ? '  ·  ${f.tags.join(' / ')}' : ''}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                              ),
                              onTap: f.isFolder ? () => _openFolder(f) : () => _preview(f),
                              trailing: PopupMenuButton<String>(
                                icon: const Icon(Icons.more_vert, size: 18),
                                onSelected: (v) => _handleMenu(v, f),
                                itemBuilder: (_) => _menuItems(f),
                              ),
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
