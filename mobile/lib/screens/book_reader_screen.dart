import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

import '../models/book_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'pdf_preview_screen.dart';

/// Reader with paragraph-level scrolling, progress, bookmarks and TTS.
class BookReaderScreen extends StatefulWidget {
  const BookReaderScreen({super.key, required this.book});

  final Book book;

  @override
  State<BookReaderScreen> createState() => _BookReaderScreenState();
}

class _BookReaderScreenState extends State<BookReaderScreen> {
  final ScrollController _scroll = ScrollController();
  final FlutterTts _tts = FlutterTts();

  List<String> _paragraphs = [];
  List<BookBookmark> _bookmarks = [];
  bool _loading = true;
  String? _error;

  Timer? _saveTimer;
  int _currentIndex = 0;
  double _progress = 0;
  bool _finished = false;

  bool _ttsReady = false;
  bool _ttsActive = false;
  bool _ttsPaused = false;
  int _ttsIndex = -1;
  double _ttsRate = 0.45;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _saveTimer?.cancel();
    try {
      _tts.stop();
    } catch (_) {}
    _persistProgress();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final detail = await ApiService().bookDetail(widget.book.id);
      final paragraphs = _split(detail.content);
      if (!mounted) return;
      setState(() {
        _paragraphs = paragraphs;
        _bookmarks = detail.bookmarks;
        _loading = false;
        _currentIndex =
            widget.book.position.clamp(0, math.max(0, paragraphs.length - 1));
        _progress = widget.book.progress.clamp(0.0, 1.0);
        _finished = detail.book.isFinished;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) => _restorePosition());
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  List<String> _split(String text) {
    final out = <String>[];
    for (final raw in text.split(RegExp(r'\n\s*\n'))) {
      final part = raw.trim();
      if (part.isEmpty) continue;
      if (part.length <= 2400) {
        out.add(part);
      } else {
        for (var i = 0; i < part.length; i += 2000) {
          out.add(part.substring(i, math.min(i + 2000, part.length)));
        }
      }
    }
    return out;
  }

  void _restorePosition() {
    if (!_scroll.hasClients || _paragraphs.isEmpty) return;
    final max = _scroll.position.maxScrollExtent;
    final ratio = _currentIndex / math.max(1, _paragraphs.length - 1);
    _scroll.jumpTo(max * ratio);
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    if (!_scroll.hasClients || _paragraphs.isEmpty) return;
    final max = _scroll.position.maxScrollExtent;
    final ratio = max <= 0 ? 0.0 : (_scroll.offset / max).clamp(0.0, 1.0);
    final index = (ratio * (_paragraphs.length - 1)).round();
    if (index != _currentIndex) {
      setState(() => _currentIndex = index);
    }
    _progress = ratio;
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 1200), _persistProgress);
  }

  void _persistProgress() {
    if (_paragraphs.isEmpty) return;
    final status =
        _progress >= 0.995 ? 'finished' : (_finished ? 'finished' : 'reading');
    ApiService()
        .updateBookProgress(
          widget.book.id,
          position: _currentIndex,
          progress: _progress,
          status: status,
        )
        .catchError((_) => widget.book);
  }

  void _jumpToParagraph(int index) {
    if (!_scroll.hasClients || _paragraphs.isEmpty) return;
    final target = index.clamp(0, _paragraphs.length - 1);
    final max = _scroll.position.maxScrollExtent;
    final ratio = target / math.max(1, _paragraphs.length - 1);
    _scroll.animateTo(
      max * ratio,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOut,
    );
    setState(() => _currentIndex = target);
  }

  Future<void> _addBookmark() async {
    final noteController = TextEditingController();
    final paragraph = _paragraphs.isEmpty
        ? ''
        : _paragraphs[_currentIndex.clamp(0, _paragraphs.length - 1)];
    final label =
        paragraph.length > 24 ? '${paragraph.substring(0, 24)}…' : paragraph;
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('添加书签'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '第 ${_currentIndex + 1} 段 · $label',
              style: const TextStyle(fontSize: 11.5, color: Colors.grey),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: noteController,
              maxLines: 3,
              decoration: const InputDecoration(
                hintText: '备注（可选）',
                isDense: true,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    final note = noteController.text.trim();
    noteController.dispose();
    if (saved != true) return;
    try {
      final bookmark = await ApiService().addBookBookmark(
        widget.book.id,
        position: _currentIndex,
        label: label,
        note: note,
      );
      if (!mounted) return;
      setState(() => _bookmarks = [..._bookmarks, bookmark]);
      _toast('已添加书签');
    } catch (e) {
      _toast('添加失败：$e');
    }
  }

  Future<void> _showBookmarks() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setSheet) {
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '书签',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 8),
                    if (_bookmarks.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 24),
                        child: Center(
                          child: Text(
                            '还没有书签',
                            style: TextStyle(fontSize: 12, color: Colors.grey),
                          ),
                        ),
                      )
                    else
                      Flexible(
                        child: ListView.builder(
                          shrinkWrap: true,
                          itemCount: _bookmarks.length,
                          itemBuilder: (_, i) {
                            final bookmark = _bookmarks[i];
                            return ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.bookmark_rounded),
                              title: Text(
                                '第 ${bookmark.position + 1} 段',
                                style: const TextStyle(fontSize: 13),
                              ),
                              subtitle: Text(
                                bookmark.note.isNotEmpty
                                    ? bookmark.note
                                    : bookmark.label,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11),
                              ),
                              onTap: () {
                                Navigator.pop(ctx);
                                _jumpToParagraph(bookmark.position);
                              },
                              trailing: IconButton(
                                icon: const Icon(
                                  Icons.delete_outline,
                                  size: 18,
                                ),
                                onPressed: () async {
                                  try {
                                    await ApiService().deleteBookBookmark(
                                      widget.book.id,
                                      bookmark.id,
                                    );
                                    setSheet(() {
                                      _bookmarks = _bookmarks
                                          .where((b) => b.id != bookmark.id)
                                          .toList();
                                    });
                                    if (mounted) setState(() {});
                                  } catch (_) {}
                                },
                              ),
                            );
                          },
                        ),
                      ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _ensureTts() async {
    if (_ttsReady) return;
    final sample = _paragraphs.take(30).join(' ');
    final latin = RegExp(r'[A-Za-z]').allMatches(sample).length;
    final cjk = RegExp(r'[\u4e00-\u9fff]').allMatches(sample).length;
    final language = latin > cjk * 2 ? 'en-US' : 'zh-CN';
    try {
      await _tts.setLanguage(language);
      await _tts.setSpeechRate(_ttsRate);
      await _tts.setPitch(1.0);
      await _tts.awaitSpeakCompletion(true);
      _ttsReady = true;
    } catch (_) {
      _ttsReady = false;
    }
  }

  List<String> _chunks(String text) {
    final chunks = <String>[];
    var buffer = StringBuffer();
    for (final char in text.split('')) {
      buffer.write(char);
      if (buffer.length >= 360 &&
          (char == '。' ||
              char == '！' ||
              char == '？' ||
              char == '.' ||
              char == '!' ||
              char == '?' ||
              char == '\n')) {
        chunks.add(buffer.toString());
        buffer = StringBuffer();
      }
    }
    if (buffer.toString().trim().isNotEmpty) chunks.add(buffer.toString());
    return chunks;
  }

  Future<void> _toggleTts() async {
    if (_ttsActive) {
      _ttsActive = false;
      try {
        await _tts.stop();
      } catch (_) {}
      if (!mounted) return;
      setState(() => _ttsPaused = true);
      return;
    }
    final from = _ttsPaused && _ttsIndex >= 0 ? _ttsIndex : _currentIndex;
    await _startTts(from);
  }

  Future<void> _startTts(int from) async {
    await _ensureTts();
    if (!_ttsReady || _paragraphs.isEmpty || !mounted) {
      _toast('当前设备不支持朗读');
      return;
    }
    _ttsActive = true;
    _ttsPaused = false;
    _ttsIndex = from.clamp(0, _paragraphs.length - 1);
    setState(() {});
    _speakLoop();
  }

  Future<void> _speakLoop() async {
    while (_ttsActive && _ttsIndex < _paragraphs.length) {
      _jumpToParagraph(_ttsIndex);
      final chunks = _chunks(_paragraphs[_ttsIndex]);
      for (final chunk in chunks) {
        if (!_ttsActive) return;
        try {
          await _tts.speak(chunk);
        } catch (_) {
          if (mounted) setState(() => _ttsActive = false);
          return;
        }
      }
      if (!_ttsActive) return;
      if (mounted) setState(() => _ttsIndex++);
    }
    if (!mounted) return;
    setState(() {
      _ttsActive = false;
      _ttsPaused = false;
      _ttsIndex = -1;
    });
  }

  Future<void> _stopTts() async {
    _ttsActive = false;
    _ttsPaused = false;
    try {
      await _tts.stop();
    } catch (_) {}
    if (mounted) setState(() => _ttsIndex = -1);
  }

  Future<void> _ttsMove(int delta) async {
    if (_paragraphs.isEmpty) return;
    final base = _ttsIndex >= 0 ? _ttsIndex : _currentIndex;
    final target = (base + delta).clamp(0, _paragraphs.length - 1);
    final wasActive = _ttsActive;
    _ttsActive = false;
    try {
      await _tts.stop();
    } catch (_) {}
    if (wasActive) {
      await _startTts(target);
    } else {
      _ttsPaused = true;
      setState(() => _ttsIndex = target);
      _jumpToParagraph(target);
    }
  }

  Future<void> _cycleRate() async {
    const rates = [0.4, 0.45, 0.5, 0.6];
    final index = rates.indexOf(_ttsRate);
    _ttsRate = rates[(index + 1) % rates.length];
    try {
      await _tts.setSpeechRate(_ttsRate);
    } catch (_) {}
    if (!mounted) return;
    setState(() {});
  }

  String get _rateLabel {
    if (_ttsRate <= 0.4) return '0.9x';
    if (_ttsRate <= 0.45) return '1.0x';
    if (_ttsRate <= 0.5) return '1.1x';
    return '1.3x';
  }

  Future<void> _markFinished() async {
    try {
      await ApiService().updateBookProgress(
        widget.book.id,
        position: _paragraphs.isEmpty ? 0 : _paragraphs.length - 1,
        progress: 1,
        status: 'finished',
      );
      if (!mounted) return;
      setState(() {
        _finished = true;
        _progress = 1;
      });
      _toast('已标记读完');
    } catch (e) {
      _toast('操作失败：$e');
    }
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  bool _isHeading(String paragraph) {
    if (paragraph.startsWith('##')) return true;
    if (paragraph.length <= 30 &&
        RegExp(r'^第.{1,10}[章节卷部]').hasMatch(paragraph)) {
      return true;
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final book = widget.book;
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        titleSpacing: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              book.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
            Text(
              [
                book.format.toUpperCase(),
                if (book.author.isNotEmpty) book.author,
                _finished ? '已读完' : '${(_progress * 100).round()}%',
              ].join(' · '),
              style: TextStyle(fontSize: 10, color: palette.muted),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: _ttsActive ? '暂停朗读' : '朗读',
            onPressed: _paragraphs.isEmpty ? null : _toggleTts,
            icon: Icon(
              _ttsActive
                  ? Icons.pause_circle_outline_rounded
                  : Icons.headphones_rounded,
            ),
          ),
          IconButton(
            tooltip: '书签',
            onPressed: _paragraphs.isEmpty ? null : _showBookmarks,
            icon: const Icon(Icons.bookmarks_outlined),
          ),
          IconButton(
            tooltip: '添加书签',
            onPressed: _paragraphs.isEmpty ? null : _addBookmark,
            icon: const Icon(Icons.bookmark_add_outlined),
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'original' && book.format == 'pdf') {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => PdfPreviewScreen(
                      fileId: book.fileId,
                      filename: '${book.title}.pdf',
                    ),
                  ),
                );
              } else if (value == 'finished') {
                _markFinished();
              } else if (value == 'restart') {
                _jumpToParagraph(0);
              }
            },
            itemBuilder: (context) => [
              if (book.format == 'pdf')
                const PopupMenuItem(
                  value: 'original',
                  child: Text('查看 PDF 原文'),
                ),
              const PopupMenuItem(
                value: 'restart',
                child: Text('回到开头'),
              ),
              const PopupMenuItem(
                value: 'finished',
                child: Text('标记读完'),
              ),
            ],
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(2),
          child: LinearProgressIndicator(
            value: _progress.clamp(0.0, 1.0),
            minHeight: 2,
            backgroundColor: palette.line,
            color: _finished ? palette.success : palette.primary,
          ),
        ),
      ),
      body: _buildBody(palette),
      bottomNavigationBar: (_ttsActive || _ttsPaused) ? _ttsBar(palette) : null,
    );
  }

  Widget _buildBody(AppPalette palette) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.menu_book_outlined, size: 30, color: palette.muted),
              const SizedBox(height: 10),
              Text(
                _error!,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: palette.ink),
              ),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('重试')),
            ],
          ),
        ),
      );
    }
    if (_paragraphs.isEmpty) {
      return Center(
        child: Text(
          '这本书没有可阅读的文字',
          style: TextStyle(fontSize: 12.5, color: palette.muted),
        ),
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
      itemCount: _paragraphs.length,
      itemBuilder: (context, index) {
        final paragraph = _paragraphs[index];
        final heading = _isHeading(paragraph);
        final highlighted = _ttsIndex == index;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          margin: const EdgeInsets.only(bottom: 10),
          padding: highlighted
              ? const EdgeInsets.symmetric(horizontal: 8, vertical: 8)
              : const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: highlighted
                ? palette.primarySoft.withValues(alpha: 0.7)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
          ),
          child: SelectableText(
            heading && paragraph.startsWith('##')
                ? paragraph.replaceFirst(RegExp(r'^##\s*'), '')
                : paragraph,
            style: TextStyle(
              fontSize: heading ? 17 : 15.5,
              height: 1.9,
              fontWeight: heading ? FontWeight.w800 : FontWeight.w400,
              color: palette.ink,
            ),
          ),
        );
      },
    );
  }

  Widget _ttsBar(AppPalette palette) {
    return Container(
      decoration: BoxDecoration(
        color: palette.card,
        border: Border(top: BorderSide(color: palette.line)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              IconButton(
                tooltip: '上一段',
                onPressed: () => _ttsMove(-1),
                icon: const Icon(Icons.skip_previous_rounded),
              ),
              IconButton(
                tooltip: _ttsActive ? '暂停' : '继续',
                onPressed: _toggleTts,
                icon: Icon(
                  _ttsActive
                      ? Icons.pause_circle_filled_rounded
                      : Icons.play_circle_filled_rounded,
                  size: 38,
                  color: palette.primary,
                ),
              ),
              IconButton(
                tooltip: '下一段',
                onPressed: () => _ttsMove(1),
                icon: const Icon(Icons.skip_next_rounded),
              ),
              TextButton(
                onPressed: _cycleRate,
                child: Text(
                  _rateLabel,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              IconButton(
                tooltip: '停止朗读',
                onPressed: _stopTts,
                icon: const Icon(Icons.stop_circle_outlined),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
