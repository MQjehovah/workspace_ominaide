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
        title: const Text('OmniAide'),
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
          Container(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                TextField(
                  controller: _chatController,
                  decoration: InputDecoration(
                    hintText: '向 AI 提问...',
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.send),
                      onPressed: () {
                        final q = _chatController.text.trim();
                        Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(initialQuery: q)));
                      },
                    ),
                  ),
                  onSubmitted: (_) {
                    final q = _chatController.text.trim();
                    Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(initialQuery: q)));
                  },
                ),
              ],
            ),
          ),

          // Quick Actions
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: [
                Row(children: [
                  _quickBtn(Icons.smart_toy, 'AI 助手', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ChatScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.event, '日程', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ScheduleScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.check_circle_outline, '待办', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const TodoScreen()))),
                ]),
                const SizedBox(height: 12),
                Row(children: [
                  _quickBtn(Icons.notifications, '通知', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const NotificationsScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.search, '搜索', () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SearchScreen()))),
                  const SizedBox(width: 12),
                  _quickBtn(Icons.refresh, '刷新', _loadRecent),
                ]),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Overview stats
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                _statCard(Icons.check_circle_outline, '待办', _todoCount),
                const SizedBox(width: 12),
                _statCard(Icons.notifications_outlined, '未读通知', _unreadCount),
                const SizedBox(width: 12),
                _statCard(Icons.event, '日程', _eventCount),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Recent Files
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              Text('最近文件', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
            ]),
          ),
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
                      return ListTile(
                        dense: true,
                        leading: Icon(f.isFolder ? Icons.folder : Icons.insert_drive_file, color: f.isFolder ? Colors.amber : Colors.blue),
                        title: Text(f.originalName, style: const TextStyle(fontSize: 14)),
                        subtitle: Text(f.sizeFormatted, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _quickBtn(IconData icon, String label, VoidCallback onTap) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade50,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.grey.shade200),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: const Color(0xFF007AFF)),
              const SizedBox(height: 6),
              Text(label, style: const TextStyle(fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statCard(IconData icon, String label, int value) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: Colors.grey.shade100,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(children: [
          Icon(icon, size: 20, color: const Color(0xFF007AFF)),
          const SizedBox(height: 4),
          Text('$value', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        ]),
      ),
    );
  }
}
