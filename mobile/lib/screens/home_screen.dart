import 'package:flutter/material.dart';
import 'dashboard_screen.dart';
import 'files_screen.dart';
import 'notes_screen.dart';
import 'music_screen.dart';
import '../services/notification_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _page = 0;
  final _pages = [const DashboardScreen(), const FilesScreen(), const NotesScreen(), const MusicScreen()];

  @override
  void initState() {
    super.initState();
    NotificationService().start(_showNotification);
  }

  @override
  void dispose() {
    NotificationService().stop();
    super.dispose();
  }

  void _showNotification(String title, String body) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(body.isEmpty ? title : '$title\n$body'), duration: const Duration(seconds: 4)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_page],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _page,
        onDestinationSelected: (i) => setState(() => _page = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: '工作台'),
          NavigationDestination(icon: Icon(Icons.folder_outlined), selectedIcon: Icon(Icons.folder), label: '文件'),
          NavigationDestination(icon: Icon(Icons.article_outlined), selectedIcon: Icon(Icons.article), label: '笔记'),
          NavigationDestination(icon: Icon(Icons.headphones_outlined), selectedIcon: Icon(Icons.headphones), label: '音乐'),
        ],
      ),
    );
  }
}
