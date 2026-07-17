import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});
  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  List<Map<String, dynamic>> _notes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadNotes();
  }

  Future<void> _loadNotes() async {
    setState(() => _loading = true);
    try {
      final res = await ApiService().get('/plugins/notes/tree');
      if (res.statusCode == 200) {
        final data = List<dynamic>.from(jsonDecode(res.body));
        _notes = _flattenTree(data);
      }
    } catch (_) {}
    if (!mounted) return;
    setState(() => _loading = false);
  }

  List<Map<String, dynamic>> _flattenTree(List<dynamic> tree, {int depth = 0}) {
    final result = <Map<String, dynamic>>[];
    for (final n in tree) {
      result.add({...Map<String, dynamic>.from(n), 'depth': depth});
      if (n['children'] != null && (n['children'] as List).isNotEmpty) {
        result.addAll(_flattenTree(n['children'], depth: depth + 1));
      }
    }
    return result;
  }

  Future<void> _createNote() async {
    try {
      await ApiService().post('/plugins/notes', {'title': '无标题', 'content': ''});
      _loadNotes();
    } catch (_) {}
  }

  void _openNote(Map<String, dynamic> note) {
    Navigator.push(context, MaterialPageRoute(
      builder: (_) => NoteEditorScreen(note: note, onSaved: _loadNotes),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('笔记'),
        actions: [
          IconButton(icon: const Icon(Icons.add), onPressed: _createNote),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _notes.isEmpty
          ? const Center(child: Text('暂无笔记', style: TextStyle(color: Colors.grey)))
          : RefreshIndicator(
              onRefresh: _loadNotes,
              child: ListView.builder(
                itemCount: _notes.length,
                itemBuilder: (_, i) {
                  final n = _notes[i];
                  final depth = n['depth'] as int? ?? 0;
                  final hasChildren = (n['children'] as List?)?.isNotEmpty ?? false;
                  return Padding(
                    padding: EdgeInsets.only(left: 16.0 * depth),
                    child: ListTile(
                      dense: true,
                      leading: Icon(hasChildren ? Icons.folder : Icons.article_outlined, size: 20),
                      title: Text(n['title'] ?? '无标题', style: const TextStyle(fontSize: 14)),
                      subtitle: n['updated_at'] != null
                        ? Text(n['updated_at'].toString().substring(0, 10), style: TextStyle(fontSize: 11, color: Colors.grey.shade500))
                        : null,
                      onTap: () => _openNote(n),
                    ),
                  );
                },
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

  @override
  void initState() {
    super.initState();
    _titleCtrl = TextEditingController(text: widget.note['title'] ?? '');
    _contentCtrl = TextEditingController(text: widget.note['content'] ?? '');
    _loadContent();
  }

  Future<void> _loadContent() async {
    final id = widget.note['id'];
    if (id == null) return;
    try {
      final res = await ApiService().get('/plugins/notes/$id');
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        _titleCtrl.text = data['title'] ?? '';
        _contentCtrl.text = data['content'] ?? '';
        if (mounted) setState(() {});
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ApiService().put('/plugins/notes/${widget.note['id']}', {
        'title': _titleCtrl.text,
        'content': _contentCtrl.text,
      });
      widget.onSaved();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已保存'), duration: Duration(seconds: 1)));
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
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _titleCtrl,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          decoration: const InputDecoration(border: InputBorder.none, hintText: '无标题'),
        ),
        actions: [
          IconButton(
            icon: _saving ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.save),
            onPressed: _saving ? null : _save,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: TextField(
          controller: _contentCtrl,
          maxLines: null,
          expands: true,
          textAlignVertical: TextAlignVertical.top,
          style: const TextStyle(fontSize: 14, height: 1.6, fontFamily: 'monospace'),
          decoration: const InputDecoration(
            border: InputBorder.none,
            hintText: '开始写点什么...',
            contentPadding: EdgeInsets.zero,
          ),
        ),
      ),
    );
  }
}
