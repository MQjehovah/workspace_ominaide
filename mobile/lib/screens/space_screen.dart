import 'package:flutter/material.dart';

import '../models/cos_models.dart';
import '../models/space_catalog.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'brief_screen.dart';
import 'device_screen.dart';
import 'files_screen.dart';
import 'inbox_screen.dart';
import 'mail_screen.dart';
import 'music_screen.dart';
import 'notes_screen.dart';
import 'notifications_screen.dart';
import 'projects_screen.dart';
import 'rss_screen.dart';
import 'schedule_screen.dart';
import 'search_screen.dart';
import 'todo_screen.dart';
import 'vibecoding_screen.dart';

class SpaceScreen extends StatefulWidget {
  const SpaceScreen({super.key});

  @override
  State<SpaceScreen> createState() => _SpaceScreenState();
}

class _SpaceScreenState extends State<SpaceScreen> {
  int _mail = 0;
  int _dingtalk = 0;
  int _notifications = 0;
  int _schedule = 0;
  int _todos = 0;
  int _projects = 0;
  int _files = 0;
  int _rss = 0;
  int _inboxTotal = 0;
  int _inboxUrgent = 0;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<T?> _safe<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  Future<void> _load() async {
    final api = ApiService();
    final now = DateTime.now();
    final start = DateTime(now.year, now.month, now.day);
    final results = await Future.wait<dynamic>([
      _safe(api.getTriage()),
      _safe(api.listNotifications(limit: 50)),
      _safe(api.listScheduleEvents(
        start: start.toIso8601String(),
        end: start.add(const Duration(days: 1)).toIso8601String(),
      )),
      _safe(api.listTodoItems(status: 'pending', pageSize: 200)),
      _safe(api.listProjects()),
      _safe(api.listFiles()),
      _safe(api.listRssEntries()),
    ]);
    if (!mounted) return;
    final triage = results[0] as TriageSnapshot?;
    final notifications = (results[1] as List<Map<String, dynamic>>?) ?? [];
    final events = (results[2] as List<Map<String, dynamic>>?) ?? [];
    final todos = (results[3] as List<Map<String, dynamic>>?) ?? [];
    final projects = (results[4] as List<Map<String, dynamic>>?) ?? [];
    final files = (results[5] as List<dynamic>?) ?? [];
    final rss = (results[6] as List<Map<String, dynamic>>?) ?? [];
    final sourceCounts = triage?.countsBySource() ?? const <String, int>{};
    final notificationUnread =
        notifications.where((n) => n['read'] == false).length;

    setState(() {
      _mail = sourceCounts['mail'] ?? 0;
      _dingtalk = sourceCounts['dingtalk'] ?? 0;
      _notifications = notificationUnread;
      _schedule = events.length;
      _todos = todos.length;
      _projects = projects.length;
      _files = files.length;
      _rss = rss.length;
      _inboxTotal = (triage?.total ?? 0) + notificationUnread;
      _inboxUrgent = triage?.urgentCount ?? 0;
      _loading = false;
    });
  }

  Future<void> _open(String key) async {
    final Widget? target = switch (key) {
      'mail' => const MailScreen(),
      'dingtalk' => const InboxScreen(initialFilter: 'dingtalk'),
      'notifications' => const NotificationsScreen(),
      'schedule' => const ScheduleScreen(),
      'todo' => const TodoScreen(),
      'projects' => const ProjectsScreen(),
      'cos' => const BriefScreen(),
      'files' => const FilesScreen(),
      'notes' => const NotesScreen(),
      'rss' => const RssScreen(),
      'music' => const MusicScreen(),
      'device' => const DeviceScreen(),
      'lab' => const VibecodingScreen(),
      _ => null,
    };
    if (target == null) return;
    await Navigator.push(context, MaterialPageRoute(builder: (_) => target));
    if (mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final groups = buildSpaceCatalog(
      mailCount: _mail,
      dingtalkCount: _dingtalk,
      notificationCount: _notifications,
      scheduleCount: _schedule,
      todoCount: _todos,
      projectCount: _projects,
      fileCount: _files,
      rssCount: _rss,
    );

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          color: palette.primary,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              PageHeader(
                kicker: 'Hub',
                title: '空间',
                subtitle: '所有应用与业务对象',
                actions: [
                  RoundIconButton(
                    icon: Icons.search_rounded,
                    tooltip: '搜索',
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const SearchScreen()),
                    ),
                  ),
                  const SizedBox(width: 6),
                  RoundIconButton(
                    icon: Icons.tune_rounded,
                    tooltip: '管理',
                    onTap: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('排序与隐藏即将支持')),
                      );
                    },
                  ),
                ],
              ),
              if (_loading)
                LinearProgressIndicator(
                  color: palette.primary,
                  backgroundColor: palette.primarySoft,
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: _InboxCard(
                  total: _inboxTotal,
                  urgent: _inboxUrgent,
                  mail: _mail,
                  dingtalk: _dingtalk,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const InboxScreen()),
                  ),
                ),
              ),
              for (final group in groups) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                  child: SectionHeader(title: group.title, actionLabel: '管理'),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 1.08,
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    children: [
                      for (final item in group.items)
                        _SpaceTile(item: item, onTap: () => _open(item.key)),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 10),
            ],
          ),
        ),
      ),
    );
  }
}

class _InboxCard extends StatelessWidget {
  const _InboxCard({
    required this.total,
    required this.urgent,
    required this.mail,
    required this.dingtalk,
    required this.onTap,
  });

  final int total;
  final int urgent;
  final int mail;
  final int dingtalk;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(13),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  palette.accent.withValues(alpha: 0.65),
                  palette.accent,
                ],
              ),
              borderRadius: BorderRadius.circular(13),
            ),
            child: const Icon(
              Icons.inbox_rounded,
              color: Colors.white,
              size: 19,
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '统一收件箱',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '$total 条待处理 · 邮件 $mail · 钉钉 $dingtalk',
                  style: TextStyle(fontSize: 10.5, color: palette.muted),
                ),
              ],
            ),
          ),
          if (urgent > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
              decoration: BoxDecoration(
                color: palette.accent.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(9),
              ),
              child: Text(
                '$urgent 紧急',
                style: TextStyle(
                  fontSize: 9.5,
                  fontWeight: FontWeight.w800,
                  color: palette.accent,
                ),
              ),
            ),
          const SizedBox(width: 2),
          Icon(Icons.chevron_right_rounded, size: 18, color: palette.muted),
        ],
      ),
    );
  }
}

class _SpaceTile extends StatelessWidget {
  const _SpaceTile({required this.item, required this.onTap});

  final SpaceItemSpec item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          decoration: BoxDecoration(
            color: palette.card,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: palette.line),
          ),
          child: Stack(
            children: [
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: item.color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(item.icon, size: 17, color: item.color),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      item.label,
                      style: TextStyle(
                        fontSize: 10.5,
                        fontWeight: FontWeight.w600,
                        color: palette.ink,
                      ),
                    ),
                  ],
                ),
              ),
              if (item.badge != null)
                Positioned(
                  top: 7,
                  right: 7,
                  child: Container(
                    constraints: const BoxConstraints(minWidth: 16),
                    height: 16,
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    decoration: BoxDecoration(
                      color: palette.accent,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      '${item.badge}',
                      style: const TextStyle(
                        fontSize: 8.5,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
