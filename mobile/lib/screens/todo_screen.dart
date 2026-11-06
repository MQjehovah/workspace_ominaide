import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/local_cache_service.dart';
import '../services/local_reminder_service.dart';

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
    setState(() => _loading = _items.isEmpty);
    if (_items.isEmpty) {
      final cached = await LocalCacheService().readList('todo');
      if (mounted && cached.isNotEmpty) {
        setState(() {
          _items = cached;
          _loading = false;
        });
      }
    }
    try {
      final items = await ApiService().listTodoItems();
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
      await LocalCacheService().writeJson('todo', items);
      LocalReminderService().syncTodos(items);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (_items.isEmpty) _items = [];
        _loading = false;
      });
      if (_items.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载失败: $e')),
        );
      }
    }
  }

  Future<void> _add() async {
    final ctl = TextEditingController();
    var priority = 0;
    DateTime? due;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('新建待办'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: ctl,
                autofocus: true,
                decoration: const InputDecoration(labelText: '内容'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                value: priority,
                decoration: const InputDecoration(labelText: '优先级'),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('普通')),
                  DropdownMenuItem(value: 1, child: Text('重要')),
                  DropdownMenuItem(value: 2, child: Text('紧急')),
                ],
                onChanged: (v) => setDialogState(() => priority = v ?? 0),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () async {
                  final date = await showDatePicker(
                    context: c,
                    initialDate: due ?? DateTime.now(),
                    firstDate: DateTime.now().subtract(const Duration(days: 365)),
                    lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
                  );
                  if (date == null || !c.mounted) return;
                  final time = await showTimePicker(
                    context: c,
                    initialTime: due == null
                        ? const TimeOfDay(hour: 18, minute: 0)
                        : TimeOfDay.fromDateTime(due!),
                  );
                  if (time == null) return;
                  setDialogState(() {
                    due = DateTime(
                      date.year,
                      date.month,
                      date.day,
                      time.hour,
                      time.minute,
                    );
                  });
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text(
                  due == null ? '设置截止时间（可选）' : '截止：${_fmtDateTime(due!)}',
                ),
              ),
              if (due != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => setDialogState(() => due = null),
                    child: const Text('清除截止时间', style: TextStyle(fontSize: 11)),
                  ),
                ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('创建')),
          ],
        ),
      ),
    );
    final title = ctl.text.trim();
    ctl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().createTodoItem({
        'title': title,
        'status': 'pending',
        'priority': priority,
        if (due != null) 'due_date': due!.toIso8601String(),
      });
      if (!mounted) return;
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<void> _edit(Map<String, dynamic> item) async {
    final id = item['id'];
    if (id is! int) return;
    final ctl = TextEditingController(text: (item['title'] ?? '').toString());
    final rawPriority = item['priority'];
    var priority = rawPriority is num
        ? rawPriority.toInt()
        : int.tryParse('$rawPriority') ?? 0;
    var due = DateTime.tryParse((item['due_date'] ?? '').toString());
    if (due != null && due.isUtc) due = due.toLocal();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('编辑待办'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: ctl,
                decoration: const InputDecoration(labelText: '内容'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                value: priority,
                decoration: const InputDecoration(labelText: '优先级'),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('普通')),
                  DropdownMenuItem(value: 1, child: Text('重要')),
                  DropdownMenuItem(value: 2, child: Text('紧急')),
                ],
                onChanged: (v) => setDialogState(() => priority = v ?? 0),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () async {
                  final date = await showDatePicker(
                    context: c,
                    initialDate: due ?? DateTime.now(),
                    firstDate: DateTime.now().subtract(const Duration(days: 365)),
                    lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
                  );
                  if (date == null || !c.mounted) return;
                  final time = await showTimePicker(
                    context: c,
                    initialTime: due == null
                        ? const TimeOfDay(hour: 18, minute: 0)
                        : TimeOfDay.fromDateTime(due!),
                  );
                  if (time == null) return;
                  setDialogState(() {
                    due = DateTime(
                      date.year,
                      date.month,
                      date.day,
                      time.hour,
                      time.minute,
                    );
                  });
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text(
                  due == null ? '设置截止时间（可选）' : '截止：${_fmtDateTime(due!)}',
                ),
              ),
              if (due != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => setDialogState(() => due = null),
                    child: const Text('清除截止时间', style: TextStyle(fontSize: 11)),
                  ),
                ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('保存')),
          ],
        ),
      ),
    );
    final title = ctl.text.trim();
    ctl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().updateTodoItem(id, {
        'title': title,
        'priority': priority,
        'due_date': due?.toIso8601String(),
      });
      if (!mounted) return;
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('保存失败: $e')));
    }
  }

  Future<void> _toggle(Map<String, dynamic> item) async {
    final id = item['id'];
    final done = item['status'] == 'done' || item['completed'] == true;
    try {
      await ApiService().updateTodoItem(
        id is int ? id : int.parse('$id'),
        {'status': done ? 'pending' : 'done'},
      );
      _load();
    } catch (_) {}
  }

  Future<void> _delete(Map<String, dynamic> item) async {
    final id = item['id'];
    if (id is! int) return;
    try {
      await ApiService().deleteTodoItem(id);
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('删除失败: $e')));
    }
  }

  String _fmtDateTime(DateTime d) {
    final h = d.hour.toString().padLeft(2, '0');
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.month}月${d.day}日 $h:$m';
  }

  (String, Color)? _priorityMeta(Map<String, dynamic> item) {
    final p = item['priority'];
    final priority = p is num ? p.toInt() : int.tryParse('$p') ?? 0;
    if (priority >= 2) return ('紧急', Colors.red);
    if (priority == 1) return ('重要', Colors.orange);
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('待办'),
        actions: [IconButton(onPressed: _add, icon: const Icon(Icons.add))],
      ),
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
                      final due = DateTime.tryParse((item['due_date'] ?? '').toString());
                      final priority = _priorityMeta(item);
                      final parts = <String>[
                        if (due != null) '截止 ${_fmtDateTime(due)}',
                        if (priority != null) priority.$1,
                      ];
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: CheckboxListTile(
                          value: done,
                          title: Text(
                            (item['title'] ?? '').toString(),
                            style: done
                                ? const TextStyle(
                                    decoration: TextDecoration.lineThrough,
                                    color: Colors.grey,
                                  )
                                : null,
                          ),
                          subtitle: parts.isEmpty
                              ? null
                              : Text(
                                  parts.join(' · '),
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: priority?.$2 ?? Colors.grey,
                                  ),
                                ),
                          onChanged: (_) => _toggle(item),
                          secondary: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                icon: const Icon(Icons.edit_outlined),
                                onPressed: () => _edit(item),
                              ),
                              IconButton(
                                icon: const Icon(Icons.delete_outline),
                                onPressed: () => _delete(item),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
