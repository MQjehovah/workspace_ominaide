import 'package:flutter/material.dart';

import '../services/local_reminder_service.dart';
import '../services/notification_service.dart';
import '../services/refresh_bus.dart';
import '../widgets/navigation_shell.dart';
import 'chat_screen.dart';
import 'profile_screen.dart';
import 'space_screen.dart';
import 'workbench_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const _pages = [
    ChatScreen(autoLoadLatest: true),
    WorkbenchScreen(),
    SpaceScreen(),
    ProfileScreen(),
  ];

  @override
  void initState() {
    super.initState();
    NotificationService().start(_showNotification);
    LocalReminderService().syncAll();
  }

  @override
  void dispose() {
    NotificationService().stop();
    super.dispose();
  }

  void _showNotification(String title, String body) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(body.isEmpty ? title : '$title\n$body'),
        duration: const Duration(seconds: 4),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return NavigationShell(
      initialIndex: 1,
      pages: _pages,
      onTabChanged: (index) {
        if (index == 1) RefreshBus.bump('workbench');
        if (index == 2) RefreshBus.bump('space');
      },
    );
  }
}
