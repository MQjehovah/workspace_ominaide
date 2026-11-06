import 'package:flutter/material.dart';
import '../services/api_service.dart';
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
    setState(() { _loading = true; _error = ''; });
    try {
      final events = await ApiService().listScheduleEvents();
      if (!mounted) return;
      setState(() { _events = events; _loading = false; });
      LocalReminderService().syncSchedule(events);
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
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
                  final date = await showDatePicker(
                    context: c,
                    initialDate: selected,
                    firstDate: DateTime.now().subtract(const Duration(days: 365)),
                    lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
                  );
                  if (date == null || !c.mounted) return;
                  final time = await showTimePicker(
                    context: c,
                    initialTime: TimeOfDay.fromDateTime(selected),
                  );
                  if (time == null) return;
                  setDialogState(() {
                    selected = DateTime(
                      date.year,
                      date.month,
                      date.day,
                      time.hour,
                      time.minute,
                    );
                  });
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
