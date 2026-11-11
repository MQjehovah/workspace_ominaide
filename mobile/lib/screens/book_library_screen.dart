import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/book_models.dart';
import '../models/file_item.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'book_reader_screen.dart';

/// File-backed ebook library: import EPUB/PDF/TXT/MD/DOCX, keep reading
/// progress, bookmarks and TTS.
class BookLibraryScreen extends StatefulWidget {
  const BookLibraryScreen({super.key});

  @override
  State<BookLibraryScreen> createState() => _BookLibraryScreenState();
}

class _BookLibraryScreenState extends State<BookLibraryScreen> {
  List<Book> _books = [];
  bool _loading = true;
  bool _adding = false;
  String _addingLabel = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final books = await ApiService().listBooks();
      if (!mounted) return;
      setState(() => _books = books);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('读取书库失败：$e')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showAddMenu() async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.folder_copy_outlined),
              title: const Text('从文件库选择'),
              subtitle: const Text('从已有的 MinIO 文件里挑选电子书'),
              onTap: () => Navigator.pop(ctx, 'files'),
            ),
            ListTile(
              leading: const Icon(Icons.upload_file_rounded),
              title: const Text('上传本地文件'),
              subtitle: const Text('从手机选择 EPUB / PDF / TXT / MD / DOCX'),
              onTap: () => Navigator.pop(ctx, 'upload'),
            ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (choice == 'files') {
      await _addFromFileLibrary();
    } else if (choice == 'upload') {
      await _addBooks();
    }
  }

  Future<void> _addFromFileLibrary() async {
    if (_adding) return;
    final selected = await showModalBottomSheet<List<int>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (_) => _BookFilePicker(
        existingFileIds: _books.map((book) => book.fileId).toSet(),
      ),
    );
    if (selected == null || selected.isEmpty) return;
    setState(() {
      _adding = true;
      _addingLabel = '0/${selected.length}';
    });
    var added = 0;
    final errors = <String>[];
    for (var i = 0; i < selected.length; i++) {
      setState(() => _addingLabel = '${i + 1}/${selected.length}');
      try {
        await ApiService().addBook(selected[i]);
        added++;
      } catch (e) {
        errors.add(
            '文件 #${selected[i]}: ${e.toString().replaceFirst('Exception: ', '')}');
      }
    }
    if (!mounted) return;
    setState(() {
      _adding = false;
      _addingLabel = '';
    });
    await _load();
    if (!mounted) return;
    if (added > 0) _toast('已加入书库 $added 本');
    if (errors.isNotEmpty) {
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('部分文件未导入'),
          content: SingleChildScrollView(
            child: Text(
              errors.join('\n\n'),
              style: const TextStyle(fontSize: 12),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('知道了'),
            ),
          ],
        ),
      );
    }
  }

  Future<void> _addBooks() async {
    if (_adding) return;
    FilePickerResult? result;
    try {
      result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: FileType.custom,
        allowedExtensions: const [
          'epub',
          'pdf',
          'txt',
          'md',
          'markdown',
          'docx'
        ],
      );
    } catch (e) {
      _toast('选择文件失败：$e');
      return;
    }
    if (result == null || result.files.isEmpty) return;
    setState(() {
      _adding = true;
      _addingLabel = '0/${result!.files.length}';
    });
    var added = 0;
    final errors = <String>[];
    for (var i = 0; i < result.files.length; i++) {
      final file = result.files[i];
      final path = file.path;
      if (path == null) continue;
      setState(() => _addingLabel = '${i + 1}/${result!.files.length}');
      try {
        final fileId = await ApiService().uploadBookFile(path, file.name);
        await ApiService().addBook(fileId);
        added++;
      } catch (e) {
        errors.add(
            '${file.name}: ${e.toString().replaceFirst('Exception: ', '')}');
      }
    }
    if (!mounted) return;
    setState(() {
      _adding = false;
      _addingLabel = '';
    });
    await _load();
    if (!mounted) return;
    if (added > 0) {
      _toast('已加入书库 $added 本');
    }
    if (errors.isNotEmpty) {
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('部分文件未导入'),
          content: SingleChildScrollView(
            child:
                Text(errors.join('\n\n'), style: const TextStyle(fontSize: 12)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('知道了'),
            ),
          ],
        ),
      );
    }
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _delete(Book book) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('移出书库'),
        content: Text('确定要移除「${book.title}」吗？原始文件不会被删除。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('移除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ApiService().deleteBook(book.id);
      await _load();
    } catch (e) {
      _toast('移除失败：$e');
    }
  }

  Future<void> _open(Book book) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => BookReaderScreen(book: book)),
    );
    if (mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Books',
              title: '书库',
              subtitle: _books.isEmpty
                  ? '从文件导入 EPUB / PDF / TXT 等电子书'
                  : '${_books.length} 本 · ${_books.where((b) => b.isReading).length} 本在读',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '添加电子书',
                  onTap: _adding ? null : _showAddMenu,
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: _load,
                ),
              ],
            ),
            if (_adding)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Row(
                  children: [
                    const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '正在导入 $_addingLabel（解析电子书可能需要一点时间）',
                      style: TextStyle(fontSize: 11, color: palette.muted),
                    ),
                  ],
                ),
              ),
            Expanded(
              child: _loading
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _books.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                const EmptyState(
                                  icon: Icons.menu_book_outlined,
                                  title: '书库还是空的',
                                  subtitle: '点右上角 + 从文件中选择电子书',
                                ),
                                const SizedBox(height: 12),
                                Center(
                                  child: FilledButton.icon(
                                    onPressed: _showAddMenu,
                                    icon: const Icon(Icons.add_rounded),
                                    label: const Text('添加电子书'),
                                  ),
                                ),
                              ],
                            )
                          : ListView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              itemCount: _books.length,
                              itemBuilder: (_, i) =>
                                  _bookTile(palette, _books[i]),
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bookTile(AppPalette palette, Book book) {
    final subtitle = [
      if (book.author.isNotEmpty) book.author,
      book.format.toUpperCase(),
      book.statusLabel,
    ].join(' · ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppCard(
        onTap: () => _open(book),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 38,
              height: 50,
              decoration: BoxDecoration(
                color: palette.primarySoft,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                book.format == 'pdf'
                    ? Icons.picture_as_pdf_outlined
                    : Icons.menu_book_rounded,
                size: 20,
                color: palette.primary,
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    book.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13.5,
                      height: 1.35,
                      fontWeight: FontWeight.w700,
                      color: palette.ink,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 10.5, color: palette.muted),
                  ),
                  const SizedBox(height: 7),
                  Row(
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(3),
                          child: LinearProgressIndicator(
                            value: book.progress.clamp(0.0, 1.0),
                            minHeight: 4,
                            backgroundColor: palette.line,
                            color: book.isFinished
                                ? palette.success
                                : palette.primary,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${(book.progress * 100).round()}%',
                        style: TextStyle(fontSize: 9.5, color: palette.muted),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              tooltip: '移出书库',
              onPressed: () => _delete(book),
              icon: Icon(
                Icons.delete_outline_rounded,
                size: 17,
                color: palette.muted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BookFilePicker extends StatefulWidget {
  const _BookFilePicker({required this.existingFileIds});

  final Set<int> existingFileIds;

  @override
  State<_BookFilePicker> createState() => _BookFilePickerState();
}

class _BookFilePickerState extends State<_BookFilePicker> {
  static const _extensions = [
    '.epub',
    '.pdf',
    '.txt',
    '.md',
    '.markdown',
    '.docx',
  ];

  final _search = TextEditingController();
  final Set<int> _selected = {};
  List<FileItem> _files = [];
  bool _loading = true;
  Timer? _searchTimer;

  @override
  void initState() {
    super.initState();
    _search.addListener(_onQueryChanged);
    _load();
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onQueryChanged() {
    setState(() {});
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 450), _load);
  }

  bool _isEbook(FileItem file) {
    final name = file.originalName.toLowerCase();
    return _extensions.any(name.endsWith);
  }

  Future<void> _load() async {
    final query = _search.text.trim();
    if (_files.isEmpty && mounted) setState(() => _loading = true);
    List<FileItem> files = [];
    try {
      files = await ApiService().listRecentFiles(
        limit: 200,
        search: query.isEmpty ? null : query,
      );
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _files = files.where(_isEbook).toList()
        ..sort((a, b) => a.originalName.compareTo(b.originalName));
      _loading = false;
    });
  }

  List<FileItem> get _visible {
    final query = _search.text.trim().toLowerCase();
    if (query.isEmpty) return _files;
    return _files
        .where((file) => file.originalName.toLowerCase().contains(query))
        .toList();
  }

  bool _isExisting(FileItem file) => widget.existingFileIds.contains(file.id);

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final visible = _visible;
    return FractionallySizedBox(
      heightFactor: 0.86,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 8, 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '从文件库选择',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: palette.ink,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: '搜索文件名…',
                prefixIcon: const Icon(Icons.search_rounded, size: 18),
                isDense: true,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : visible.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Text(
                            _files.isEmpty
                                ? '文件库里还没有 EPUB / PDF / TXT 等电子书。\n可以先用「上传本地文件」导入，或在文件模块上传。'
                                : '没有匹配的文件',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 12,
                              height: 1.7,
                              color: palette.muted,
                            ),
                          ),
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        itemCount: visible.length,
                        itemBuilder: (_, index) {
                          final file = visible[index];
                          final existing = _isExisting(file);
                          final selected = _selected.contains(file.id);
                          final name = file.originalName;
                          final ext = name.contains('.')
                              ? name.split('.').last.toUpperCase()
                              : 'FILE';
                          return CheckboxListTile(
                            value: existing || selected,
                            onChanged: existing
                                ? null
                                : (value) {
                                    setState(() {
                                      if (value == true) {
                                        _selected.add(file.id);
                                      } else {
                                        _selected.remove(file.id);
                                      }
                                    });
                                  },
                            controlAffinity: ListTileControlAffinity.leading,
                            title: Text(
                              name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 13,
                                color: existing ? palette.muted : palette.ink,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            subtitle: Text(
                              existing
                                  ? '已在书库'
                                  : '$ext · ${_fmtSize(file.size)} · ${file.folderPath}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 10.5,
                                color: palette.muted,
                              ),
                            ),
                            secondary: Icon(
                              Icons.menu_book_rounded,
                              size: 18,
                              color: existing ? palette.muted : palette.primary,
                            ),
                          );
                        },
                      ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _selected.isEmpty
                      ? null
                      : () => Navigator.pop(context, _selected.toList()),
                  child: Text(
                    _selected.isEmpty
                        ? '选择要加入书库的文件'
                        : '加入书库（${_selected.length}）',
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _fmtSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
