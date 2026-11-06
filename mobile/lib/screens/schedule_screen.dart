import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/local_cache_service.dart';
import '../services/local_reminder_service.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});
  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  List<Map<String, dynamic>> _events = [];
  bool _loading = true;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = _events.isEmpty;
      _error = '';
    });
    if (_events.isEmpty) {
      final cached = await LocalCacheService().readList('schedule');
      if (mounted && cached.isNotEmpty) {
        setState(() {
          _events = cached;
          _loading = false;
        });
      }
    }
    try {
      final events = await ApiService().listScheduleEvents();
      if (!mounted) return;
      setState(() {
        _events = events;
        _loading = false;
      });
      await LocalCacheService().writeJson('schedule', events);
      LocalReminderService().syncSchedule(events);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (_events.isEmpty) _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _add() async {
    final titleCtl = TextEditingController();
    var selected = DateTime.now().add(const Duration(hours: 1));
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('新建日程'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: titleCtl,
                decoration: const InputDecoration(labelText: '标题'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final picked = await _pickDateTime(c, selected);
                  if (picked == null) return;
                  setDialogState(() => selected = picked);
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text('时间：${_fmtDateTime(selected)}'),
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
    final title = titleCtl.text.trim();
    titleCtl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().createScheduleEvent({
        'title': title,
        'start_time': selected.toUtc().toIso8601String(),
        'end_time': selected.add(const Duration(hours: 1)).toUtc().toIso8601String(),
      });
      if (!mounted) return;
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<DateTime?> _pickDateTime(BuildContext context, DateTime initial) async {
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
    );
    if (date == null || !context.mounted) return null;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null) return null;
    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  Future<void> _edit(Map<String, dynamic> event) async {
    final id = (event['id'] as num?)?.toInt();
    if (id == null) return;
    final titleCtl = TextEditingController(text: (event['title'] ?? '').toString());
    var selected = DateTime.tryParse((event['start_time'] ?? '').toString()) ??
        DateTime.now().add(const Duration(hours: 1));
    if (selected.isUtc) selected = selected.toLocal();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('编辑日程'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: titleCtl,
                decoration: const InputDecoration(labelText: '标题'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final picked = await _pickDateTime(c, selected);
                  if (picked == null) return;
                  setDialogState(() => selected = picked);
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text('时间：${_fmtDateTime(selected)}'),
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
    final title = titleCtl.text.trim();
    titleCtl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().updateScheduleEvent(id, {
        'title': title,
        'start_time': selected.toUtc().toIso8601String(),
        'end_time': selected.add(const Duration(hours: 1)).toUtc().toIso8601String(),
      });
      if (!mounted) return;
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('保存失败: $e')));
    }
  }
  String _fmtDateTime(DateTime d) {
    final h = d.hour.toString().padLeft(2, '0');
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.month}月${d.day}日 $h:$m';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('日程'), actions: [IconButton(onPressed: _add, icon: const Icon(Icons.add))]),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error.isNotEmpty
              ? Center(child: Text(_error, style: const TextStyle(color: Colors.red)))
              : _events.isEmpty
                  ? const Center(child: Text('暂无日程'))
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        itemCount: _events.length,
                        itemBuilder: (c, i) {
                          final e = _events[i];
                          return Card(
                            margin: const EdgeInsets.only(bottom: 8),
                            child: ListTile(
                              leading: CircleAvatar(backgroundColor: Theme.of(context).colorScheme.primaryContainer, child: Icon(Icons.event, color: Theme.of(context).colorScheme.primary)),
                              title: Text(e['title'] ?? '无标题'),
                              subtitle: Text(_fmtTime(e['start_time']?.toString())),
                              onTap: () => _edit(e),
                              trailing: IconButton(
                                icon: const Icon(Icons.delete_outline),
                                onPressed: () async {
                                  final id = e['id'];
                                  if (id is int) { await ApiService().deleteScheduleEvent(id); _load(); }
                                },
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }

  String _fmtTime(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) { return iso; }
  }
}
