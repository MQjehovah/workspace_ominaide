import 'package:flutter/material.dart';

import '../models/opencode_models.dart';
import '../services/local_reminder_service.dart';
import '../services/notification_service.dart';
import '../services/opencode_run_monitor.dart';
import '../services/refresh_bus.dart';
import '../widgets/navigation_shell.dart';
import 'chat_screen.dart';
import 'opencode_session_screen.dart';
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

  final OpenCodeRunMonitor _runMonitor = OpenCodeRunMonitor();

  @override
  void initState() {
    super.initState();
    NotificationService().start(_showNotification);
    LocalReminderService().syncAll();
    _runMonitor.onCompleted = _onRunCompleted;
    _runMonitor.onPermission = _onPermission;
    _runMonitor.onForm = _onForm;
    _runMonitor.start();
  }

  @override
  void dispose() {
    _runMonitor.onCompleted = null;
    _runMonitor.onPermission = null;
    _runMonitor.onForm = null;
    _runMonitor.stop();
    NotificationService().stop();
    super.dispose();
  }

  void _onRunCompleted(OpenCodeRun run) {
    if (!mounted) return;
    final failed = run.status == 'failed';
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          '${run.title} ${failed ? '执行失败' : '执行完成'}'
          ' · ${formatRunDuration(run.elapsed)}',
        ),
        duration: const Duration(seconds: 6),
        action: SnackBarAction(
          label: '查看',
          onPressed: () => _openRun(run, busy: false),
        ),
      ),
    );
  }

  void _onPermission(OpenCodeRun run) {
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text('${run.title} 需要确认：${run.permissionAction}'),
        duration: const Duration(seconds: 8),
        action: SnackBarAction(
          label: '去处理',
          onPressed: () => _openRun(run, busy: true),
        ),
      ),
    );
  }

  void _onForm(OpenCodeRun run) {
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text('${run.title} 需要你选择：${run.formTitle}'),
        duration: const Duration(seconds: 8),
        action: SnackBarAction(
          label: '去选择',
          onPressed: () => _openRun(run, busy: true),
        ),
      ),
    );
  }

  void _openRun(OpenCodeRun run, {required bool busy}) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => OpenCodeSessionScreen(
          machineId: run.machineId,
          session: OpenCodeSession(
            id: run.sessionId,
            title: run.title,
            directory: run.directory,
            busy: busy,
          ),
        ),
      ),
    );
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
