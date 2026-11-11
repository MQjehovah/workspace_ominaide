import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/book_models.dart';
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
                  tooltip: '从文件导入',
                  onTap: _adding ? null : _addBooks,
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
                                    onPressed: _addBooks,
                                    icon: const Icon(Icons.add_rounded),
                                    label: const Text('从文件导入'),
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
