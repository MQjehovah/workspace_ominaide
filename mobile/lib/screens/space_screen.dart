import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/cos_models.dart';
import '../models/file_item.dart';
import '../models/space_catalog.dart';
import '../services/api_service.dart';
import '../services/cos_repository.dart';
import '../services/event_time.dart';
import '../services/refresh_bus.dart';
import '../services/seen_state_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'automation_screen.dart';
import 'device_screen.dart';
import 'dingtalk_actions_screen.dart';
import 'files_screen.dart';
import 'insights_screen.dart';
import 'inbox_screen.dart';
import 'mail_screen.dart';
import 'meeting_minutes_screen.dart';
import 'music_screen.dart';
import 'notes_screen.dart';
import 'notifications_screen.dart';
import 'projects_screen.dart';
import 'sources_screen.dart';
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
  int _sources = 0;
  int _inboxTotal = 0;
  int _inboxUrgent = 0;
  bool _loading = true;
  bool _error = false;
  Set<String> _hidden = {};

  static const _hiddenKey = 'space.hidden';
  late final ValueNotifier<int> _refresh = RefreshBus.signal('space');

  @override
  void initState() {
    super.initState();
    _refresh.addListener(_onRefreshSignal);
    _loadHidden();
    _load();
  }

  @override
  void dispose() {
    _refresh.removeListener(_onRefreshSignal);
    super.dispose();
  }

  void _onRefreshSignal() {
    if (mounted) _load(force: true);
  }

  Future<void> _loadHidden() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => _hidden = (prefs.getStringList(_hiddenKey) ?? []).toSet());
  }

  Future<void> _toggleHidden(String key) async {
    final next = Set<String>.from(_hidden);
    if (next.contains(key)) {
      next.remove(key);
    } else {
      next.add(key);
    }
    setState(() => _hidden = next);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_hiddenKey, next.toList());
  }

  Future<void> _showManage() async {
    final groups = buildSpaceCatalog();
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (sheetContext) {
        final palette = AppPalette.of(sheetContext);
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                children: [
                  Row(
                    children: [
                      Text(
                        '管理空间',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: palette.ink,
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () async {
                          setState(() => _hidden = {});
                          if (sheetContext.mounted) {
                            setSheetState(() => _hidden = {});
                          }
                          final prefs = await SharedPreferences.getInstance();
                          await prefs.remove(_hiddenKey);
                        },
                        child: const Text('全部显示'),
                      ),
                    ],
                  ),
                  Text(
                    '隐藏不常用的入口，随时可以恢复。',
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                  const SizedBox(height: 6),
                  for (final group in groups) ...[
                    Padding(
                      padding: const EdgeInsets.only(top: 8, bottom: 2),
                      child: Text(
                        group.title,
                        style: TextStyle(
                          fontSize: 10,
                          letterSpacing: 1,
                          fontWeight: FontWeight.w700,
                          color: palette.muted,
                        ),
                      ),
                    ),
                    for (final item in group.items)
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        value: !_hidden.contains(item.key),
                        thumbColor: WidgetStatePropertyAll(palette.primary),
                        title: Text(
                          item.label,
                          style: TextStyle(fontSize: 13, color: palette.ink),
                        ),
                        secondary: Icon(
                          item.icon,
                          size: 18,
                          color: item.color,
                        ),
                        onChanged: (value) async {
                          await _toggleHidden(item.key);
                          if (!sheetContext.mounted) return;
                          setSheetState(() {});
                        },
                      ),
                  ],
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<T?> _safe<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  Future<void> _load({bool force = false}) async {
    final api = ApiService();
    final now = DateTime.now();
    final start = DateTime(now.year, now.month, now.day);
    final results = await Future.wait<dynamic>([
      _safe(cosRepository.getTriage(force: force)),
      _safe(api.listNotifications(limit: 50)),
      _safe(api.listScheduleEvents(
        start: start.toIso8601String(),
        end: start.add(const Duration(days: 1)).toIso8601String(),
      )),
      _safe(api.listTodoItems(status: 'pending', pageSize: 200)),
      _safe(api.listProjects()),
      _safe(api.listFiles()),
      _safe(api.listSourceItems()),
    ]);
    if (!mounted) return;
    final triage = results[0] as TriageSnapshot?;
    final notifications = (results[1] as List<Map<String, dynamic>>?) ?? [];
    final events = (results[2] as List<Map<String, dynamic>>?) ?? [];
    final todos = (results[3] as List<Map<String, dynamic>>?) ?? [];
    final projects = (results[4] as List<Map<String, dynamic>>?) ?? [];
    final files = (results[5] as List?)?.whereType<FileItem>().toList() ??
        const <FileItem>[];
    final sources = (results[6] as List<Map<String, dynamic>>?) ?? [];
    final notificationUnread =
        notifications.where((n) => n['read'] == false).length;

    // File badges show files added since the user last opened Files.
    final filesSeenAt = await SeenStateService().filesSeenAt();
    final filesBaseline = filesSeenAt ?? DateTime.now();
    if (filesSeenAt == null) {
      await SeenStateService().markFilesSeen(filesBaseline);
    }
    final newFiles = files.where((file) {
      final created = DateTime.tryParse(file.createdAt)?.toLocal();
      return created != null && created.isAfter(filesBaseline);
    }).length;

    setState(() {
      _error = results.every((value) => value == null);
      // Mail/files/sources badges describe unread or new content, not totals.
      _mail = triage?.unreadCount('mail') ?? 0;
      _dingtalk = triage?.bySource('dingtalk').length ?? 0;
      _notifications = notificationUnread;
      _schedule = events.where((event) => !eventHasEnded(event)).length;
      _todos = todos.length;
      _projects = projects.length;
      _files = newFiles;
      _sources = sources.where((item) => item['read'] != true).length;
      _inboxTotal = (triage?.pendingCount ?? 0) + notificationUnread;
      _inboxUrgent = triage?.urgentCount ?? 0;
      _loading = false;
    });
  }

  Future<void> _open(String key) async {
    final Widget? target = switch (key) {
      'inbox' => const InboxScreen(),
      'mail' => const MailScreen(),
      'dingtalk' => const DingTalkActionsScreen(),
      'notifications' => const NotificationsScreen(),
      'schedule' => const ScheduleScreen(),
      'minutes' => const MeetingMinutesScreen(),
      'todo' => const TodoScreen(),
      'projects' => const ProjectsScreen(),
      'insights' => const InsightsScreen(),
      'automation' => const AutomationScreen(),
      'files' => const FilesScreen(),
      'notes' => const NotesScreen(),
      'sources' => const SourcesScreen(),
      'music' => const MusicScreen(),
      'device' => const DeviceScreen(),
      'lab' => const VibecodingScreen(),
      _ => null,
    };
    if (target == null) return;
    await Navigator.push(context, MaterialPageRoute(builder: (_) => target));
    if (key == 'files') {
      await SeenStateService().markFilesSeen();
    }
    if (mounted) _load(force: true);
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final allGroups = buildSpaceCatalog(
      mailCount: _mail,
      dingtalkCount: _dingtalk,
      notificationCount: _notifications,
      scheduleCount: _schedule,
      todoCount: _todos,
      projectCount: _projects,
      fileCount: _files,
      sourceCount: _sources,
    );
    final groups = [
      for (final group in allGroups)
        if (group.items.any((item) => !_hidden.contains(item.key)))
          SpaceGroupSpec(
            title: group.title,
            items: group.items
                .where((item) => !_hidden.contains(item.key))
                .toList(),
          ),
    ];

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => _load(force: true),
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
                    onTap: _showManage,
                  ),
                ],
              ),
              if (_loading)
                LinearProgressIndicator(
                  color: palette.primary,
                  backgroundColor: palette.primarySoft,
                ),
              if (_error)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: InlineErrorBanner(
                    onRetry: () => _load(force: true),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: _InboxCard(
                  total: _inboxTotal,
                  urgent: _inboxUrgent,
                  mail: _mail,
                  dingtalk: _dingtalk,
                  onTap: () async {
                    await Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const InboxScreen()),
                    );
                    if (mounted) _load(force: true);
                  },
                ),
              ),
              for (final group in groups) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                  child: SectionHeader(
                    title: group.title,
                    actionLabel: '管理',
                    onAction: _showManage,
                  ),
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
                  '收件箱',
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
