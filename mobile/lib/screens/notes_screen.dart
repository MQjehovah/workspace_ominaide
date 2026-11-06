import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

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
