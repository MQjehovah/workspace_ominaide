import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';
import '../services/notes_import_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'note_versions_screen.dart';
import 'notes_ask_screen.dart';
import 'photo_scan_screen.dart';
import 'voice_note_screen.dart';

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});
  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  List<Map<String, dynamic>> _notes = [];
  final Set<int> _collapsed = {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadNotes();
  }

  Future<void> _loadNotes() async {
    setState(() { _loading = true; _error = null; });
    try {
      final res = await ApiService().get('/plugins/notes/tree');
      if (res.statusCode == 200) {
        final data = ApiService().decodeJson(res);
        _notes = data is List ? _flattenTree(data) : [];
      } else {
        _error = '服务器错误: ${res.statusCode}';
      }
    } catch (e) {
      _error = '连接失败: $e';
    }
    if (!mounted) return;
    setState(() => _loading = false);
  }

  List<Map<String, dynamic>> _flattenTree(List<dynamic> tree, {int depth = 0}) {
    final result = <Map<String, dynamic>>[];
    for (final n in tree) {
      final map = Map<String, dynamic>.from(n as Map);
      map['depth'] = depth;
      result.add(map);
      final children = map['children'] as List?;
      if (children != null && children.isNotEmpty) {
        result.addAll(_flattenTree(children, depth: depth + 1));
      }
    }
    return result;
  }

  Future<void> _createNote() async {
    try {
      final res = await ApiService().post('/plugins/notes', {'title': '无标题', 'content': ''});
      if (res.statusCode == 201) {
        await _loadNotes();
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: ${res.statusCode}')));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _createChild(Map<String, dynamic> parent) async {
    final parentId = parent['id'];
    if (parentId == null) return;
    try {
      final res = await ApiService().post('/plugins/notes', {'title': '无标题', 'content': '', 'parent_id': parentId});
      if (res.statusCode == 201) {
        _collapsed.remove(parentId);
        await _loadNotes();
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: ${res.statusCode}')));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _deleteNote(Map<String, dynamic> note) async {
    final id = note['id'];
    if (id == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('删除笔记'),
        content: Text('确定删除「${note['title'] ?? '无标题'}」?子笔记也会一并删除。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('删除', style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().delete('/plugins/notes/$id');
      await _loadNotes();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('删除失败: $e')));
    }
  }

  void _openNote(Map<String, dynamic> note) {
    if (_isFolder(note)) {
      _toggleFolder(note);
      return;
    }
    Navigator.push(context, MaterialPageRoute(
      builder: (_) => NoteEditorScreen(note: note, onSaved: _loadNotes),
    ));
  }

  Future<void> _openNoteById(int noteId, String title) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => NoteEditorScreen(
          note: {'id': noteId, 'title': title},
          onSaved: _loadNotes,
        ),
      ),
    );
    if (mounted) _loadNotes();
  }

  Future<void> _openAsk() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => NotesAskScreen(onOpenNote: _openNoteById),
      ),
    );
  }

  Future<void> _showNotesMenu() async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.search, color: palette.primary),
              title: const Text('搜索笔记'),
              subtitle: const Text('按标题和正文搜索'),
              onTap: () {
                Navigator.pop(ctx);
                _searchNotes();
              },
            ),
            ListTile(
              leading: Icon(Icons.file_upload_outlined, color: palette.primary),
              title: const Text('从文件导入'),
              subtitle: const Text('PDF / Word / HTML / 文本 / 音频'),
              onTap: () {
                Navigator.pop(ctx);
                _importFile();
              },
            ),
            ListTile(
              leading: Icon(Icons.link, color: palette.primary),
              title: const Text('从 URL 导入'),
              subtitle: const Text('抓取网页正文并生成笔记'),
              onTap: () {
                Navigator.pop(ctx);
                _importUrl();
              },
            ),
            ListTile(
              leading: Icon(Icons.mic_none_rounded, color: palette.primary),
              title: const Text('语音笔记'),
              subtitle: const Text('录音后自动转写并生成笔记'),
              onTap: () {
                Navigator.pop(ctx);
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => VoiceNoteScreen(
                      onOpenNote: _openNoteById,
                    ),
                  ),
                );
              },
            ),
            ListTile(
              leading: Icon(Icons.document_scanner_outlined, color: palette.primary),
              title: const Text('拍照扫描'),
              subtitle: const Text('识别纸质文档/白板文字并保存为笔记'),
              onTap: () {
                Navigator.pop(ctx);
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => PhotoScanScreen(
                      onOpenNote: _openNoteById,
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Future<void> _searchNotes() async {
    final note = await showSearch<Map<String, dynamic>?>(
      context: context,
      delegate: _NotesSearchDelegate(),
    );
    if (!mounted || note == null) return;
    _openNote(note);
  }

  Future<void> _importFile() async {
    final result = await FilePicker.platform.pickFiles();
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null) return;
    try {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('正在导入，请稍候…')),
        );
      }
      await NotesImportService().importFile(file.path!, file.name);
      await _loadNotes();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('笔记已导入')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('导入失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _importUrl() async {
    final ctl = TextEditingController();
    final url = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('从 URL 导入'),
        content: TextField(
          controller: ctl,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(
            hintText: 'https://example.com/article',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
            child: const Text('导入'),
          ),
        ],
      ),
    );
    ctl.dispose();
    if (!mounted || url == null || url.isEmpty) return;
    try {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('正在抓取网页…')),
        );
      }
      await ApiService().importNoteFromUrl(url);
      await _loadNotes();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('笔记已导入')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('导入失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  bool _isFolder(Map<String, dynamic> note) =>
      note['is_folder'] == true || note['is_folder'] == 1;

  int? _noteId(Map<String, dynamic> note) {
    final id = note['id'];
    if (id is int) return id;
    return int.tryParse('$id');
  }

  void _toggleFolder(Map<String, dynamic> note) {
    final id = _noteId(note);
    if (id == null) return;
    setState(() {
      if (!_collapsed.remove(id)) _collapsed.add(id);
    });
  }

  List<Map<String, dynamic>> get _visibleNotes {
    final parents = <int, int?>{};
    for (final note in _notes) {
      final id = _noteId(note);
      if (id == null) continue;
      final rawParent = note['parent_id'];
      parents[id] = rawParent is int
          ? rawParent
          : int.tryParse('$rawParent');
    }
    bool hiddenByAncestor(Map<String, dynamic> note) {
      var parent = parents[_noteId(note)];
      var guard = 0;
      while (parent != null && guard < 100) {
        if (_collapsed.contains(parent)) return true;
        parent = parents[parent];
        guard++;
      }
      return false;
    }
    return _notes.where((note) => !hiddenByAncestor(note)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final visible = _visibleNotes;
    final folderCount = _notes.where(_isFolder).length;
    final noteCount = _notes.length - folderCount;
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Notes',
              title: '笔记',
              subtitle: '$noteCount 篇笔记 · $folderCount 个文件夹',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.more_horiz,
                  tooltip: '搜索与导入',
                  onTap: _showNotesMenu,
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.auto_awesome,
                  tooltip: '问笔记',
                  onTap: _openAsk,
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建笔记',
                  onTap: _createNote,
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary),
                    )
                  : _error != null
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _loadNotes),
                          ],
                        )
                      : _notes.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                EmptyState(
                                  icon: Icons.article_outlined,
                                  title: '还没有笔记',
                                  subtitle: '新建一篇，或从文件导入。',
                                  action: FilledButton.icon(
                                    onPressed: _createNote,
                                    icon: const Icon(Icons.add, size: 17),
                                    label: const Text('新建笔记'),
                                    style: FilledButton.styleFrom(
                                      backgroundColor: palette.primary,
                                    ),
                                  ),
                                ),
                              ],
                            )
                          : RefreshIndicator(
                              onRefresh: _loadNotes,
                              color: palette.primary,
                              child: ListView.builder(
                                physics: const AlwaysScrollableScrollPhysics(),
                                padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                                itemCount: visible.length,
                                itemBuilder: (_, i) {
                                  final note = visible[i];
                                  final depth = note['depth'] as int? ?? 0;
                                  final folder = _isFolder(note);
                                  final id = _noteId(note);
                                  final collapsed =
                                      id != null && _collapsed.contains(id);
                                  final childCount =
                                      (note['children'] as List?)?.length ?? 0;
                                  final updated =
                                      (note['updated_at'] ?? '').toString();
                                  final date = updated.length >= 10
                                      ? updated.substring(0, 10)
                                      : '';
                                  final subtitle = folder
                                      ? '文件夹${childCount > 0 ? ' · $childCount 项' : ''}'
                                      : (date.isEmpty ? '笔记' : date);

                                  return Padding(
                                    padding: EdgeInsets.only(
                                      left: 12.0 * depth,
                                      bottom: 8,
                                    ),
                                    child: AppCard(
                                      padding: EdgeInsets.zero,
                                      onTap: () => _openNote(note),
                                      child: Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 12,
                                          vertical: 10,
                                        ),
                                        child: Row(
                                          children: [
                                            Container(
                                              width: 36,
                                              height: 36,
                                              decoration: BoxDecoration(
                                                color: folder
                                                    ? palette.accent
                                                        .withValues(alpha: 0.12)
                                                    : palette.primarySoft,
                                                borderRadius:
                                                    BorderRadius.circular(11),
                                              ),
                                              child: Icon(
                                                folder
                                                    ? (collapsed
                                                        ? Icons.folder_rounded
                                                        : Icons.folder_open_rounded)
                                                    : Icons.article_outlined,
                                                size: 18,
                                                color: folder
                                                    ? palette.accent
                                                    : palette.primary,
                                              ),
                                            ),
                                            const SizedBox(width: 10),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    (note['title'] ?? '无标题')
                                                        .toString(),
                                                    maxLines: 1,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                    style: TextStyle(
                                                      fontSize: 13.5,
                                                      fontWeight:
                                                          FontWeight.w700,
                                                      color: palette.ink,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 2),
                                                  Text(
                                                    subtitle,
                                                    style: TextStyle(
                                                      fontSize: 10.5,
                                                      color: palette.muted,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                            if (folder)
                                              Icon(
                                                collapsed
                                                    ? Icons
                                                        .chevron_right_rounded
                                                    : Icons.expand_more_rounded,
                                                size: 18,
                                                color: palette.muted,
                                              ),
                                            PopupMenuButton<String>(
                                              icon: Icon(
                                                Icons.more_horiz_rounded,
                                                size: 18,
                                                color: palette.muted,
                                              ),
                                              onSelected: (value) {
                                                if (value == 'child') {
                                                  _createChild(note);
                                                } else if (value == 'delete') {
                                                  _deleteNote(note);
                                                }
                                              },
                                              itemBuilder: (_) => const [
                                                PopupMenuItem(
                                                  value: 'child',
                                                  child: Text('新建子笔记'),
                                                ),
                                                PopupMenuItem(
                                                  value: 'delete',
                                                  child: Text(
                                                    '删除',
                                                    style: TextStyle(
                                                      color: Colors.red,
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
            ),
          ],
        ),
      ),
    );
  }
}

class NoteEditorScreen extends StatefulWidget {
  final Map<String, dynamic> note;
  final VoidCallback onSaved;
  const NoteEditorScreen({super.key, required this.note, required this.onSaved});

  @override
  State<NoteEditorScreen> createState() => _NoteEditorScreenState();
}

class _NoteEditorScreenState extends State<NoteEditorScreen> {
  late TextEditingController _titleCtrl;
  late TextEditingController _contentCtrl;
  bool _saving = false;
  bool _preview = true;
  String _originalText = '';
  String _markdown = '';

  @override
  void initState() {
    super.initState();
    _titleCtrl = TextEditingController(text: widget.note['title'] ?? '');
    _contentCtrl = TextEditingController();
    _loadContent();
  }

  Future<void> _loadContent() async {
    final id = widget.note['id'];
    if (id == null) return;
    try {
      final res = await ApiService().get('/plugins/notes/$id');
      if (res.statusCode == 200) {
        final data = ApiService().decodeJson(res);
        _titleCtrl.text = data['title'] ?? '';
        final raw = data['content'] ?? '';
        final markdown = ApiService().parseNoteMarkdown(raw.toString());
        _contentCtrl.text = markdown;
        _markdown = markdown;
        _originalText = markdown;
        if (mounted) setState(() {});
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final text = _contentCtrl.text;
      final payload = <String, dynamic>{'title': _titleCtrl.text};
      // The web editor saves Markdown (`getMarkdown()`), so mobile writes the
      // same format instead of flattening the note into ProseMirror JSON.
      if (text != _originalText) {
        payload['content'] = text;
      }
      final res = await ApiService().put('/plugins/notes/${widget.note['id']}', payload);
      if (res.statusCode == 200) {
        _originalText = text;
        _markdown = text;
        widget.onSaved();
        if (!mounted) return;
        setState(() => _preview = true);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已保存'), duration: Duration(seconds: 1)));
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('保存失败: ${res.statusCode}')));
      }
    } catch (_) {}
    if (mounted) setState(() => _saving = false);
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _contentCtrl.dispose();
    super.dispose();
  }

  int? get _noteId {
    final id = widget.note['id'];
    if (id is int) return id;
    return int.tryParse('$id');
  }

  Future<void> _showMore() async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.history, color: palette.primary),
              title: const Text('版本历史'),
              subtitle: const Text('查看并恢复之前的保存版本'),
              onTap: () {
                Navigator.pop(ctx);
                _showVersions();
              },
            ),
            ListTile(
              leading: Icon(Icons.hub_outlined, color: palette.primary),
              title: const Text('相关笔记'),
              subtitle: const Text('基于语义相似度找相关笔记'),
              onTap: () {
                Navigator.pop(ctx);
                _showSimilar();
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Future<void> _showVersions() async {
    final id = _noteId;
    if (id == null) return;
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => NoteVersionsScreen(
          noteId: id,
          noteTitle: _titleCtrl.text,
        ),
      ),
    );
    if (changed == true && mounted) {
      await _loadContent();
    }
  }

  Future<void> _showSimilar() async {
    final id = _noteId;
    if (id == null) return;
    final navigator = Navigator.of(context, rootNavigator: true);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    List<Map<String, dynamic>> results;
    try {
      results = await ApiService().similarNotes(id);
    } catch (e) {
      if (mounted) {
        try {
          navigator.pop();
        } catch (_) {}
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('查找失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
      return;
    }
    if (!mounted) return;
    try {
      navigator.pop();
    } catch (_) {}
    if (results.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('没有找到相关笔记')),
      );
      return;
    }
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            Text(
              '相关笔记',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w800,
                color: palette.ink,
              ),
            ),
            const SizedBox(height: 8),
            for (final item in results)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text((item['title'] ?? '未命名笔记').toString()),
                subtitle: Text(
                  (item['snippet'] ?? '').toString(),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                onTap: () {
                  final id = (item['note_id'] as num?)?.toInt();
                  if (id == null) return;
                  Navigator.pop(ctx);
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => NoteEditorScreen(
                        note: {'id': id, 'title': item['title'] ?? '笔记'},
                        onSaved: widget.onSaved,
                      ),
                    ),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(8, 4, 10, 8),
              decoration: BoxDecoration(
                color: palette.card.withValues(alpha: 0.78),
                border: Border(bottom: BorderSide(color: palette.line)),
              ),
              child: Row(
                children: [
                  RoundIconButton(
                    icon: Icons.chevron_left_rounded,
                    onTap: () => Navigator.maybePop(context),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: _titleCtrl,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        color: palette.ink,
                      ),
                      decoration: InputDecoration(
                        border: InputBorder.none,
                        hintText: '无标题',
                        hintStyle: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: palette.muted,
                        ),
                        isDense: true,
                        contentPadding: EdgeInsets.zero,
                      ),
                    ),
                  ),
                  RoundIconButton(
                    icon: _preview
                        ? Icons.edit_outlined
                        : Icons.visibility_outlined,
                    tooltip: _preview ? '编辑' : '预览',
                    onTap: () {
                      setState(() {
                        if (_preview) {
                          _preview = false;
                        } else {
                          _markdown = _contentCtrl.text;
                          _preview = true;
                        }
                      });
                    },
                  ),
                  const SizedBox(width: 6),
                  RoundIconButton(
                    icon: Icons.more_horiz,
                    tooltip: '更多',
                    onTap: _showMore,
                  ),
                  const SizedBox(width: 6),
                  if (_saving)
                    SizedBox(
                      width: 36,
                      height: 36,
                      child: Center(
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: palette.primary,
                        ),
                      ),
                    )
                  else
                    RoundIconButton(
                      icon: Icons.save_rounded,
                      tooltip: '保存',
                      onTap: _save,
                    ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                child: AppCard(
                  padding: const EdgeInsets.all(16),
                  child: _preview
                      ? Markdown(
                          data: _markdown.trim().isEmpty ? '_空笔记_' : _markdown,
                          selectable: true,
                          padding: EdgeInsets.zero,
                          styleSheet: MarkdownStyleSheet(
                            p: TextStyle(
                              fontSize: 14,
                              height: 1.75,
                              color: palette.ink,
                            ),
                            h1: TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                            h2: TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                            h3: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: palette.ink,
                            ),
                            code: TextStyle(
                              fontSize: 12,
                              color: palette.primary,
                              backgroundColor: palette.primarySoft,
                            ),
                            codeblockDecoration: BoxDecoration(
                              color: palette.primarySoft,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            blockquoteDecoration: BoxDecoration(
                              color: palette.primarySoft,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            listBullet: TextStyle(
                              fontSize: 14,
                              color: palette.ink,
                            ),
                            a: TextStyle(
                              color: palette.primary,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        )
                      : TextField(
                          controller: _contentCtrl,
                          maxLines: null,
                          expands: true,
                          textAlignVertical: TextAlignVertical.top,
                          style: TextStyle(
                            fontSize: 14,
                            height: 1.7,
                            color: palette.ink,
                          ),
                          decoration: InputDecoration(
                            border: InputBorder.none,
                            hintText: '开始写点什么…',
                            hintStyle: TextStyle(color: palette.muted),
                            contentPadding: EdgeInsets.zero,
                          ),
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NotesSearchDelegate extends SearchDelegate<Map<String, dynamic>?> {
  _NotesSearchDelegate() : super(searchFieldLabel: '搜索笔记');

  @override
  List<Widget> buildActions(BuildContext context) => [
        if (query.isNotEmpty)
          IconButton(
            icon: const Icon(Icons.clear),
            onPressed: () => query = '',
          ),
      ];

  @override
  Widget buildLeading(BuildContext context) => IconButton(
        icon: const Icon(Icons.arrow_back),
        onPressed: () => close(context, null),
      );

  @override
  Widget buildResults(BuildContext context) => _build(context);

  @override
  Widget buildSuggestions(BuildContext context) => _build(context);

  Widget _build(BuildContext context) {
    final text = query.trim();
    if (text.isEmpty) {
      return const Center(child: Text('输入关键词搜索笔记'));
    }
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: ApiService().searchNotes(text),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Text(
              '搜索失败: ${snapshot.error}',
              style: const TextStyle(fontSize: 12),
            ),
          );
        }
        final notes = snapshot.data ?? const <Map<String, dynamic>>[];
        if (notes.isEmpty) {
          return const Center(child: Text('没有找到相关笔记'));
        }
        final palette = AppPalette.of(context);
        return ListView.builder(
          itemCount: notes.length,
          itemBuilder: (context, index) {
            final note = notes[index];
            final content = (note['content'] ?? '').toString().replaceAll('\n', ' ');
            return ListTile(
              title: Text(
                (note['title'] ?? '未命名笔记').toString(),
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: palette.ink,
                ),
              ),
              subtitle: content.isEmpty
                  ? null
                  : Text(
                      content,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 11, color: palette.muted),
                    ),
              onTap: () => close(context, note),
            );
          },
        );
      },
    );
  }
}
