import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../models/file_item.dart';
import 'search_screen.dart';
import 'chat_screen.dart';
import 'schedule_screen.dart';
import 'todo_screen.dart';
import 'notifications_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _chatController = TextEditingController();
  List<FileItem> _recentFiles = [];
  bool _loadingFiles = true;
  int _todoCount = 0;
  int _unreadCount = 0;
  int _eventCount = 0;

  @override
  void initState() {
    super.initState();
    _loadRecent();
    _loadStats();
  }

  Future<void> _loadStats() async {
    try {
      final api = ApiService();
      final todos = await api.listTodoItems();
      final notifs = await api.listNotifications();
      final events = await api.listScheduleEvents();
      if (!mounted) return;
      setState(() {
        _todoCount = todos.length;
        _unreadCount = notifs.where((n) => n['read'] == false).length;
        _eventCount = events.length;
      });
    } catch (e) {
      debugPrint('[dashboard] stats error: $e');
    }
  }

  Future<void> _loadRecent() async {
    final files = await ApiService().listFiles();
    if (!mounted) return;
    setState(() { _recentFiles = files; _loadingFiles = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('工作台'),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SearchScreen())),
          ),
        ],
      ),
      body: Column(
        children: [
          // AI Chat Input
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: TextField(
              controller: _chatController,
              decoration: InputDecoration(
                hintText: '向 AI 提问...',
                prefixIcon: const Icon(Icons.smart_toy_outlined),
                suffixIcon: IconButton(icon: const Icon(Icons.send_rounded), onPressed: () {
                  final q = _chatController.text.trim();
                  Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(initialQuery: q)));
                }),
              ),
              onSubmitted: (_) {
                final q = _chatController.text.trim();
                Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(initialQuery: q)));
              },
            ),
          ),

          // Overview stats
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                _statCard(Icons.check_circle_outline, '待办', _todoCount, () => Navigator.push(context, MaterialPageRoute(builder: (_) => const TodoScreen()))),
                const SizedBox(width: 12),
                _statCard(Icons.notifications_outlined, '未读通知', _unreadCount, () => Navigator.push(context, MaterialPageRoute(builder: (_) => const NotificationsScreen()))),
                const SizedBox(width: 12),
                _statCard(Icons.event, '日程', _eventCount, () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ScheduleScreen()))),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Quick Actions
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: [
                Row(children: [
                  _quickBtn(Icons.smart_toy, 'AI 助手', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ChatScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.search, '搜索', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SearchScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.refresh, '刷新', _loadRecent),
                ]),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Recent Files
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              Text('最近文件', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Theme.of(context).colorScheme.primary)),
            ]),
          ),
          const SizedBox(height: 4),
          Expanded(
            child: _loadingFiles
              ? const Center(child: CircularProgressIndicator())
              : _recentFiles.isEmpty
                ? const Center(child: Text('暂无文件', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _recentFiles.length,
                    itemBuilder: (_, i) {
                      final f = _recentFiles[i];
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          dense: true,
                          leading: Icon(f.isFolder ? Icons.folder_rounded : Icons.insert_drive_file_rounded, color: f.isFolder ? Colors.amber : Theme.of(context).colorScheme.primary),
                          title: Text(f.originalName, style: const TextStyle(fontSize: 14)),
                          subtitle: Text(f.sizeFormatted, style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.outline)),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _quickBtn(IconData icon, String label, VoidCallback onTap) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 18),
          decoration: BoxDecoration(
            color: scheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: scheme.primary),
              const SizedBox(height: 6),
              Text(label, style: TextStyle(fontSize: 12, color: scheme.onSurface)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statCard(IconData icon, String label, int value, VoidCallback onTap) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            color: scheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 20, color: scheme.primary),
              const SizedBox(height: 4),
              Text('$value', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: scheme.onSurface)),
              Text(label, style: TextStyle(fontSize: 11, color: scheme.outline)),
            ],
          ),
        ),
      ),
    );
  }
}
