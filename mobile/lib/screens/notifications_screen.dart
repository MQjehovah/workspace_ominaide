import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'goals_screen.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<Map<String, dynamic>> _items = [];
  List<Map<String, dynamic>> _approvals = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        ApiService().listNotifications(),
        ApiService().pendingApprovals(),
      ]);
      if (!mounted) return;
      setState(() {
        _items = results[0];
        _approvals = results[1];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _items = []; _approvals = []; _loading = false; });
    }
  }

  Future<void> _decideApproval(
    Map<String, dynamic> approval, {
    required bool approved,
    bool remember = false,
  }) async {
    final id = (approval['id'] as num?)?.toInt();
    if (id == null) return;
    try {
      await ApiService().decideApproval(
        id,
        approved: approved,
        remember: remember,
      );
      if (!mounted) return;
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('审批失败：${e.toString().replaceFirst('Exception: ', '')}')),
      );
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
                    if (result['proposal'] != null) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已处理提案')));
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const GoalsScreen()),
                      );
                    } else if (result['todo_id'] != null) {
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

  Widget _approvalCard(Map<String, dynamic> approval) {
    final tool = (approval['tool_name'] ?? '工具').toString();
    final reason = (approval['reason'] ?? '').toString();
    final risk = (approval['risk_level'] ?? '').toString();
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.lock_outline, size: 16, color: Colors.orange),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    tool,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                if (risk.isNotEmpty)
                  Text(
                    risk,
                    style: const TextStyle(fontSize: 10, color: Colors.grey),
                  ),
              ],
            ),
            if (reason.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(reason, style: const TextStyle(fontSize: 12)),
            ],
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: () =>
                        _decideApproval(approval, approved: true),
                    child: const Text('允许'),
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _decideApproval(
                      approval,
                      approved: true,
                      remember: true,
                    ),
                    child: const Text('总是允许'),
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () =>
                        _decideApproval(approval, approved: false),
                    child: const Text('拒绝'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
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
          : (_items.isEmpty && _approvals.isEmpty)
              ? const Center(child: Text('暂无通知'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    children: [
                      if (_approvals.isNotEmpty) ...[
                        const Padding(
                          padding: EdgeInsets.only(bottom: 6, left: 2),
                          child: Text(
                            '待审批',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        for (final a in _approvals) _approvalCard(a),
                        const SizedBox(height: 10),
                      ],
                      for (final n in _items)
                        Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            leading: Icon(
                              n['read'] == false
                                  ? Icons.notifications_active
                                  : Icons.notifications,
                              color: n['read'] == false
                                  ? Colors.blue
                                  : Colors.grey,
                            ),
                            title: Text(
                              n['title'] ?? '通知',
                              style: TextStyle(
                                fontWeight: n['read'] == false
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                              ),
                            ),
                            subtitle: Text(n['body'] ?? ''),
                            isThreeLine:
                                (n['body'] ?? '').toString().length > 40,
                            onTap: () => _open(n),
                          ),
                        ),
                    ],
                  ),
                ),
    );
  }
}
