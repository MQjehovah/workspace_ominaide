import 'package:flutter/material.dart';
import '../services/api_service.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
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
      final items = await ApiService().listNotifications();
      if (!mounted) return;
      setState(() { _items = items; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _items = []; _loading = false; });
    }
  }

  Future<void> _markRead() async {
    await ApiService().markNotificationsRead();
    _load();
  }

  Future<void> _open(Map<String, dynamic> n) async {
    final id = n['id'];
    if (id is! int) return;
    final api = ApiService();
    if (n['read'] == false) {
      await api.markNotificationRead(id);
    }
    final actions = (n['actions'] as List?)?.whereType<Map>().toList() ?? [];
    if (actions.isNotEmpty && mounted) {
      await showModalBottomSheet<void>(
        context: context,
        builder: (c) => SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                title: Text(n['title'] ?? '通知', style: const TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text(n['body'] ?? ''),
              ),
              const Divider(height: 1),
              for (final a in actions)
                ListTile(
                  leading: const Icon(Icons.bolt_outlined),
                  title: Text((a['label'] ?? a['key'] ?? '执行').toString()),
                  onTap: () async {
                    Navigator.pop(c);
                    final result = await api.actOnNotification(id, (a['key'] ?? a['kind']).toString());
                    if (!mounted) return;
                    if (result['todo_id'] != null) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已完成待办')));
                    } else if (result['scheduled_at'] != null) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已稍后提醒')));
                    }
                    _load();
                  },
                ),
            ],
          ),
        ),
      );
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('通知'),
        actions: [IconButton(onPressed: _markRead, icon: const Icon(Icons.done_all), tooltip: '全部已读')],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? const Center(child: Text('暂无通知'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    itemCount: _items.length,
                    itemBuilder: (c, i) {
                      final n = _items[i];
                      final unread = n['read'] == false;
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          leading: Icon(unread ? Icons.notifications_active : Icons.notifications, color: unread ? Colors.blue : Colors.grey),
                          title: Text(n['title'] ?? '通知', style: TextStyle(fontWeight: unread ? FontWeight.bold : FontWeight.normal)),
                          subtitle: Text(n['body'] ?? ''),
                          isThreeLine: (n['body'] ?? '').toString().length > 40,
                          onTap: () => _open(n),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
