import 'package:flutter/material.dart';
import '../services/api_service.dart';

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
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _add() async {
    final titleCtl = TextEditingController();
    final dateCtl = TextEditingController(text: _nowIso());
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('新建日程'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: titleCtl, decoration: const InputDecoration(labelText: '标题')),
            const SizedBox(height: 8),
            TextField(controller: dateCtl, decoration: const InputDecoration(labelText: '开始时间 (ISO)')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('创建')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().createScheduleEvent({
        'title': titleCtl.text,
        'start_time': dateCtl.text,
        'end_time': null,
      });
      _load();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  String _nowIso() {
    final now = DateTime.now().toUtc();
    return now.toIso8601String();
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
                        itemCount: _events.length,
                        itemBuilder: (c, i) {
                          final e = _events[i];
                          return ListTile(
                            leading: const Icon(Icons.event),
                            title: Text(e['title'] ?? '无标题'),
                            subtitle: Text(_fmtTime(e['start_time']?.toString())),
                            trailing: IconButton(
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () async {
                                final id = e['id'];
                                if (id is int) { await ApiService().deleteScheduleEvent(id); _load(); }
                              },
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
