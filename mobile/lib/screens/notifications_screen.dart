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
                    itemCount: _items.length,
                    itemBuilder: (c, i) {
                      final n = _items[i];
                      return ListTile(
                        leading: Icon(Icons.notifications, color: n['read'] == false ? Colors.blue : Colors.grey),
                        title: Text(n['title'] ?? '通知'),
                        subtitle: Text(n['body'] ?? ''),
                        isThreeLine: (n['body'] ?? '').toString().length > 40,
                        onTap: () {},
                      );
                    },
                  ),
                ),
    );
  }
}
