import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/file_item.dart';
import '../services/api_service.dart';
import '../services/file_transfer_service.dart';
import '../services/seen_state_service.dart';
import '../theme/app_theme.dart';
import '../widgets/loading_state.dart';
import 'audio_preview_screen.dart';
import 'pdf_preview_screen.dart';
import 'text_preview_screen.dart';

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
  final _searchController = TextEditingController();
  Timer? _searchTimer;
  String _search = '';

  @override
  void initState() {
    super.initState();
    SeenStateService().markFilesSeen();
    _loadFiles();
  }

  @override
  void dispose() {
    // Also clear after leaving so uploads made during the visit count as seen.
    SeenStateService().markFilesSeen();
    _searchTimer?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadFiles() async {
    setState(() => _loading = true);
    final files = await ApiService().listFiles(
      folderPath: _currentPath,
      search: _search.isEmpty ? null : _search,
    );
    files.sort((a, b) {
      if (a.isFolder != b.isFolder) return a.isFolder ? -1 : 1;
      return b.createdAt.compareTo(a.createdAt);
    });
    if (!mounted) return;
    setState(() {
      _files = files;
      _loading = false;
    });
  }

  void _onSearchChanged(String value) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() => _search = value.trim());
      _loadFiles();
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
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            TextButton(
                onPressed: () => Navigator.pop(ctx, c.text),
                child: const Text('创建')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _uploadFile() async {
    final result = await FilePicker.platform.pickFiles();
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null) return;
    try {
      await _withProgress('正在上传', (onProgress) async {
        await FileTransferService().upload(
          file.path!,
          file.name,
          _currentPath,
          onProgress: onProgress,
        );
      });
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('上传失败: $e')));
    }
  }

  Future<void> _withProgress(
    String title,
    Future<void> Function(void Function(int sent, int total)) task,
  ) async {
    final progress = ValueNotifier<double?>(null);
    final dialog = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: ValueListenableBuilder<double?>(
          valueListenable: progress,
          builder: (_, value, __) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              LinearProgressIndicator(value: value),
              const SizedBox(height: 10),
              Text(
                value == null
                    ? '准备中…'
                    : '${(value * 100).clamp(0, 100).toStringAsFixed(0)}%',
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
    try {
      await task((sent, total) {
        if (total > 0) progress.value = sent / total;
      });
    } finally {
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
    }
    await dialog;
    WidgetsBinding.instance.addPostFrameCallback((_) => progress.dispose());
  }

  String _ext(FileItem f) => f.originalName.split('.').last.toLowerCase();

  bool _isImage(FileItem f) =>
      ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'bmp'].contains(_ext(f));

  bool _isPdf(FileItem f) =>
      _ext(f) == 'pdf' || (f.mimeType ?? '').toLowerCase() == 'application/pdf';

  bool _isText(FileItem f) {
    final mime = (f.mimeType ?? '').toLowerCase();
    return mime.startsWith('text/') ||
        [
          'txt',
          'md',
          'markdown',
          'json',
          'csv',
          'log',
          'xml',
          'yaml',
          'yml',
        ].contains(_ext(f));
  }

  bool _isAudio(FileItem f) {
    final mime = (f.mimeType ?? '').toLowerCase();
    return mime.startsWith('audio/') ||
        ['mp3', 'm4a', 'wav', 'aac', 'flac', 'ogg', 'opus'].contains(_ext(f));
  }

  String _previewKind(FileItem f) {
    if (_isPdf(f)) return 'PDF 文档';
    if (_isImage(f)) return '图片';
    if (_isText(f)) return '文本';
    if (_isAudio(f)) return '音频';
    if (_isStreamable(f)) return '音视频';
    return '文件';
  }

  bool _canPreview(FileItem f) =>
      _isPdf(f) || _isImage(f) || _isText(f) || _isAudio(f) || _isStreamable(f);

  bool _isStreamable(FileItem f) => [
        'mp4',
        'mov',
        'm4v',
        'webm',
        'mkv',
        'mp3',
        'm4a',
        'wav',
        'aac',
        'flac',
        'ogg',
        'pdf',
      ].contains(_ext(f));

  Future<void> _showFileInfo(FileItem f) async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: palette.primarySoft,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        _isPdf(f)
                            ? Icons.picture_as_pdf_outlined
                            : _isImage(f)
                                ? Icons.image_outlined
                                : _isAudio(f)
                                    ? Icons.audio_file_outlined
                                    : Icons.insert_drive_file_outlined,
                        color: palette.primary,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            f.originalName,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '${_previewKind(f)} · ${f.sizeFormatted}'
                            '${f.createdAt.isNotEmpty ? ' · ${f.createdAt.substring(0, 10)}' : ''}',
                            style: TextStyle(
                              fontSize: 10.5,
                              color: palette.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                if (f.tags.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 5,
                    runSpacing: 5,
                    children: [
                      for (final tag in f.tags)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 7,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: palette.primarySoft,
                            borderRadius: BorderRadius.circular(7),
                          ),
                          child: Text(
                            tag,
                            style: TextStyle(
                              fontSize: 9,
                              color: palette.primary,
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
                const SizedBox(height: 12),
                if (_canPreview(f))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading:
                        Icon(Icons.visibility_outlined, color: palette.primary),
                    title: Text(
                      _isAudio(f) ? '播放' : '预览',
                      style: TextStyle(color: palette.ink),
                    ),
                    subtitle: Text(
                      '在 App 内打开，不跳转浏览器',
                      style: TextStyle(fontSize: 10, color: palette.muted),
                    ),
                    onTap: () {
                      Navigator.pop(sheetContext);
                      _preview(f);
                    },
                  ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.download_rounded, color: palette.primary),
                  title: Text('下载到本机', style: TextStyle(color: palette.ink)),
                  subtitle: Text(
                    '需要确认后才会开始下载',
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _downloadFile(f);
                  },
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.link_rounded, color: palette.primary),
                  title: Text('复制分享链接', style: TextStyle(color: palette.ink)),
                  subtitle: Text(
                    '生成临时访问链接',
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _shareLink(f);
                  },
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.share_outlined, color: palette.primary),
                  title: Text('系统分享', style: TextStyle(color: palette.ink)),
                  subtitle: Text(
                    '下载后通过系统分享面板发送',
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _shareFile(f);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _downloadFile(FileItem f) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('下载到本机？'),
        content: Text('${f.originalName}\n${f.sizeFormatted}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('下载'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      File? downloaded;
      await _withProgress('正在下载', (onProgress) async {
        downloaded = await FileTransferService().download(
          f.id,
          f.originalName,
          onProgress: onProgress,
        );
      });
      if (!mounted || downloaded == null) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('下载完成'),
          content: SelectableText(
            downloaded!.path,
            style: const TextStyle(fontSize: 11),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(context);
                Share.shareXFiles(
                  [XFile(downloaded!.path)],
                  text: f.originalName,
                );
              },
              child: const Text('分享'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('下载失败: $e')),
      );
    }
  }

  Future<void> _preview(FileItem f) async {
    if (_isPdf(f)) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => PdfPreviewScreen(
            fileId: f.id,
            filename: f.originalName,
          ),
        ),
      );
      return;
    }
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
                    title: Text(f.originalName,
                        style: const TextStyle(fontSize: 14)),
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
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('预览失败: $e')));
      }
      return;
    }
    if (_isText(f)) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => TextPreviewScreen(
            fileId: f.id,
            filename: f.originalName,
          ),
        ),
      );
      return;
    }
    if (_isAudio(f)) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => AudioPreviewScreen(
            fileId: f.id,
            filename: f.originalName,
          ),
        ),
      );
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
      File? downloaded;
      await _withProgress('正在下载', (onProgress) async {
        downloaded = await FileTransferService().download(
          f.id,
          f.originalName,
          onProgress: onProgress,
        );
      });
      if (!mounted || downloaded == null) return;
      await Share.shareXFiles([XFile(downloaded!.path)], text: f.originalName);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('下载失败: $e')));
    }
  }

  Future<void> _shareLink(FileItem f) async {
    try {
      final data = await ApiService().shareFileLink(f.id);
      final url = (data['url'] ?? '').toString();
      if (url.isEmpty) throw Exception('没有生成分享链接');
      await Clipboard.setData(ClipboardData(text: url));
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('分享链接已复制'),
          content: SelectableText(
            url,
            style: const TextStyle(fontSize: 11),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(context);
                Share.share(url, subject: f.originalName);
              },
              child: const Text('系统分享'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('生成分享链接失败: $e')),
      );
    }
  }

  Future<void> _toggleFavorite(FileItem f) async {
    try {
      await ApiService().toggleFavoriteFile(f.id);
      await _loadFiles();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('操作失败: $e')));
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
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('重命名失败: $e')));
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
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('移动失败: $e')));
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
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('保存失败: $e')));
    }
  }

  Future<void> _delete(FileItem f) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除文件'),
        content: Text('确定删除「${f.originalName}」？文件会进入回收站。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('删除失败: $e')));
    }
  }

  Widget _sectionHeader(String label, int count, {double top = 0}) {
    return Padding(
      padding: EdgeInsets.fromLTRB(16, top + 8, 16, 4),
      child: Row(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: Colors.grey.shade600,
              letterSpacing: 0.6,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            '$count',
            style: TextStyle(fontSize: 10, color: Colors.grey.shade400),
          ),
        ],
      ),
    );
  }

  Widget _fileTile(FileItem f) {
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
      onTap: f.isFolder ? () => _openFolder(f) : () => _showFileInfo(f),
      trailing: PopupMenuButton<String>(
        icon: const Icon(Icons.more_vert, size: 18),
        onSelected: (v) => _handleMenu(v, f),
        itemBuilder: (_) => _menuItems(f),
      ),
    );
  }

  List<PopupMenuEntry<String>> _menuItems(FileItem f) {
    return [
      if (!f.isFolder) ...[
        const PopupMenuItem(value: 'preview', child: Text('预览/打开')),
        const PopupMenuItem(value: 'share', child: Text('分享 / 存储到文件')),
        const PopupMenuItem(value: 'share_link', child: Text('复制分享链接')),
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
      case 'share_link':
        await _shareLink(f);
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
    final folders = _files.where((f) => f.isFolder).toList();
    final files = _files.where((f) => !f.isFolder).toList();
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
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              controller: _searchController,
              onChanged: _onSearchChanged,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: '搜索文件',
                prefixIcon: const Icon(Icons.search_rounded, size: 18),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close_rounded, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _search = '');
                          _loadFiles();
                        },
                      ),
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                GestureDetector(
                    onTap: _goRoot, child: const Icon(Icons.home, size: 18)),
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
                        final path =
                            '/' + crumbs.sublist(0, e.key + 1).join('/');
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
                ? const SkeletonList(count: 6)
                : _files.isEmpty
                    ? const Center(
                        child:
                            Text('空文件夹', style: TextStyle(color: Colors.grey)),
                      )
                    : RefreshIndicator(
                        onRefresh: _loadFiles,
                        child: ListView(
                          children: [
                            if (folders.isNotEmpty) ...[
                              _sectionHeader('文件夹', folders.length),
                              ...folders.map(_fileTile),
                            ],
                            if (files.isNotEmpty) ...[
                              _sectionHeader(
                                '文件',
                                files.length,
                                top: folders.isNotEmpty ? 10 : 0,
                              ),
                              ...files.map(_fileTile),
                            ],
                          ],
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}
