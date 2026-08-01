import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../models/file_item.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});
  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _api = ApiService();
  final _controller = TextEditingController();
  bool _loading = false;
  String _query = '';
  List<FileItem> _files = [];
  List<Map<String, dynamic>> _articles = [];
  List<Map<String, dynamic>> _semantic = [];

  Future<void> _search() async {
    final q = _controller.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _loading = true;
      _query = q;
      _files = [];
      _articles = [];
      _semantic = [];
    });
    try {
      final result = await _api.searchAll(q);
      if (!mounted) return;
      setState(() {
        _files = (result['files'] as List? ?? []).cast<FileItem>();
        _articles = (result['articles'] as List? ?? []).cast<Map<String, dynamic>>();
        _semantic = (result['semantic'] as List? ?? []).cast<Map<String, dynamic>>();
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('搜索失败')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          autofocus: true,
          textInputAction: TextInputAction.search,
          decoration: const InputDecoration(hintText: '搜索文件 / 资讯 / 笔记', border: InputBorder.none),
          onSubmitted: (_) => _search(),
        ),
        actions: [
          IconButton(onPressed: _search, icon: const Icon(Icons.search)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : (_query.isEmpty
              ? const Center(child: Text('输入关键词搜索你的数据', style: TextStyle(color: Colors.grey)))
              : _buildResults()),
    );
  }

  Widget _buildResults() {
    final total = _files.length + _articles.length + _semantic.length;
    if (total == 0) {
      return const Center(child: Text('无匹配结果', style: TextStyle(color: Colors.grey)));
    }
    return ListView(
      children: [
        if (_files.isNotEmpty) ...[
          _sectionTitle('文件', Icons.folder_outlined),
          ..._files.map((f) => ListTile(
            leading: const Icon(Icons.insert_drive_file_outlined),
            title: Text(f.originalName, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(f.mimeType ?? '文件'),
          )),
        ],
        if (_articles.isNotEmpty) ...[
          _sectionTitle('资讯', Icons.article_outlined),
          ..._articles.map((a) => ListTile(
            leading: const Icon(Icons.newspaper),
            title: Text((a['title'] as String?) ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
          )),
        ],
        if (_semantic.isNotEmpty) ...[
          _sectionTitle('语义搜索', Icons.auto_awesome),
          ..._semantic.map((s) => ListTile(
            leading: const Icon(Icons.tips_and_updates_outlined),
            title: Text((s['title'] as String?) ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text((s['snippet'] as String?) ?? '', maxLines: 2, overflow: TextOverflow.ellipsis),
          )),
        ],
      ],
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Row(children: [
        Icon(icon, size: 16, color: Colors.grey),
        const SizedBox(width: 6),
        Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Colors.grey)),
      ]),
    );
  }
}
