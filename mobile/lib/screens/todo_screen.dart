import 'package:flutter/material.dart';
import '../services/api_service.dart';

class TodoScreen extends StatefulWidget {
  const TodoScreen({super.key});
  @override
  State<TodoScreen> createState() => _TodoScreenState();
}

class _TodoScreenState extends State<TodoScreen> {
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final items = await ApiService().listTodoItems();
      if (!mounted) return;
      setState(() { _items = items; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _items = []; _loading = false; });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('加载失败: $e')));
    }
  }

  Future<void> _add() async {
    final ctl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('新建待办'),
        content: TextField(controller: ctl, autofocus: true, decoration: const InputDecoration(labelText: '内容')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('创建')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().createTodoItem({'title': ctl.text, 'status': 'pending', 'priority': 0});
      _load();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _toggle(Map<String, dynamic> item) async {
    final id = item['id'];
    final done = item['status'] == 'done' || item['completed'] == true;
    try {
      await ApiService().updateTodoItem(id is int ? id : int.parse('$id'), {'status': done ? 'pending' : 'done'});
      _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('待办'), actions: [IconButton(onPressed: _add, icon: const Icon(Icons.add))]),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? const Center(child: Text('暂无待办'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    itemCount: _items.length,
                    itemBuilder: (c, i) {
                      final item = _items[i];
                      final done = item['status'] == 'done' || item['completed'] == true;
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: CheckboxListTile(
                          value: done,
                          title: Text(item['title'] ?? '', style: done ? const TextStyle(decoration: TextDecoration.lineThrough, color: Colors.grey) : null),
                          subtitle: Text(item['created_at']?.toString().substring(0, 16) ?? ''),
                          onChanged: (_) => _toggle(item),
                          secondary: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              final id = item['id'];
                              if (id is int) { await ApiService().deleteTodoItem(id); _load(); }
                            },
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
