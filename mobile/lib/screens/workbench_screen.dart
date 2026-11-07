import 'package:flutter/material.dart';

import '../models/cos_models.dart';
import '../models/file_item.dart';
import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../services/cos_repository.dart';
import '../services/event_time.dart';
import '../services/refresh_bus.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'brief_screen.dart';
import 'chat_screen.dart';
import 'inbox_screen.dart';
import 'library_screen.dart';
import 'schedule_screen.dart';
import 'search_screen.dart';
import 'todo_screen.dart';

class WorkbenchScreen extends StatefulWidget {
  const WorkbenchScreen({super.key});

  @override
  State<WorkbenchScreen> createState() => _WorkbenchScreenState();
}

class _WorkbenchScreenState extends State<WorkbenchScreen> {
  final _chatController = TextEditingController();
  DailyBrief? _brief;
  TriageSnapshot? _triage;
  List<Map<String, dynamic>> _events = [];
  List<Map<String, dynamic>> _todos = [];
  List<FileItem> _files = [];
  int _unreadNotifications = 0;
  String _name = '';
  String _botName = '';
  bool _loading = true;
  bool _error = false;
  late final ValueNotifier<int> _refresh = RefreshBus.signal('workbench');

  @override
  void initState() {
    super.initState();
    _refresh.addListener(_onRefreshSignal);
    _load();
  }

  void _onRefreshSignal() {
    if (mounted) _load(force: true);
  }

  Future<T?> _safe<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  Future<void> _load({bool force = false}) async {
    await BotSelectionService().load();
    final api = ApiService();
    final now = DateTime.now();
    final start = DateTime(now.year, now.month, now.day);
    final end = start.add(const Duration(days: 1));

    final results = await Future.wait<dynamic>([
      _safe(cosRepository.getDailyBrief(force: force)),
      _safe(cosRepository.getTriage(force: force)),
      _safe(api.listNotifications(limit: 50)),
      _safe(api.listScheduleEvents(
        start: start.toIso8601String(),
        end: end.toIso8601String(),
      )),
      _safe(api.listTodoItems(status: 'pending', pageSize: 200)),
      _safe(api.listFiles()),
      _safe(api.getMe()),
    ]);

    if (!mounted) return;
    final me = results[6] as Map<String, dynamic>?;
    final notifications = (results[2] as List<Map<String, dynamic>>?) ?? [];
    setState(() {
      _error = results[0] == null &&
          results[1] == null &&
          results[3] == null &&
          results[4] == null &&
          results[5] == null;
      _brief = results[0] as DailyBrief?;
      _triage = results[1] as TriageSnapshot?;
      _events = (results[3] as List<Map<String, dynamic>>?) ?? [];
      _todos = (results[4] as List<Map<String, dynamic>>?) ?? [];
      _files = (results[5] as List<FileItem>?) ?? [];
      _unreadNotifications =
          notifications.where((n) => n['read'] == false).length;
      _name = (me?['display_name'] ?? me?['username'] ?? '').toString();
      _botName = BotSelectionService().botName ?? '';
      _loading = false;
    });
  }

  void _ask(String text) {
    final value = text.trim();
    if (value.isEmpty) return;
    _chatController.clear();
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => ChatScreen(initialQuery: value)),
    );
  }

  Future<void> _pushAndRefresh(Widget page) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => page));
    if (mounted) _load(force: true);
  }

  String get _greeting {
    final hour = DateTime.now().hour;
    if (hour < 11) return '早上好';
    if (hour < 18) return '下午好';
    return '晚上好';
  }

  String get _todayLabel {
    final now = DateTime.now();
    const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    return '${now.month} 月 ${now.day} 日 周${weekdays[now.weekday - 1]}';
  }

  int get _dueToday {
    final now = DateTime.now();
    final end = DateTime(now.year, now.month, now.day).add(const Duration(days: 1));
    var count = 0;
    for (final todo in _todos) {
      final due = DateTime.tryParse('${todo['due_date'] ?? ''}');
      if (due == null) continue;
      if (!due.isBefore(now) && due.isBefore(end)) count++;
    }
    return count;
  }

  int get _overdue {
    final now = DateTime.now();
    var count = 0;
    for (final todo in _todos) {
      final due = DateTime.tryParse('${todo['due_date'] ?? ''}');
      if (due != null && due.isBefore(now)) count++;
    }
    return count;
  }

  String _eventTime(Map<String, dynamic> event) {
    final raw = '${event['start_time'] ?? ''}';
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return '';
    return '${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
  }

  @override
  void dispose() {
    _refresh.removeListener(_onRefreshSignal);
    _chatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final inboxCount = (_triage?.pendingCount ?? 0) + _unreadNotifications;
    final urgent = _triage?.urgentCount ?? 0;
    final sourceCounts = <String, int>{
      'mail': _triage?.unreadCount('mail') ?? 0,
      'dingtalk': _triage?.bySource('dingtalk').length ?? 0,
    };

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => _load(force: true),
          color: palette.primary,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 22),
            children: [
              PageHeader(
                kicker: 'Workbench',
                title: '$_greeting，${_name.isEmpty ? '你好' : _name}',
                subtitle: _todayLabel,
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
                  _Avatar(name: _name),
                ],
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  children: [
                    if (_error) ...[
                      InlineErrorBanner(onRetry: () => _load(force: true)),
                      const SizedBox(height: 9),
                    ],
                    _buildHeroChat(palette),
                    const SizedBox(height: 9),
                    _buildTodayCard(palette),
                    const SizedBox(height: 9),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: _buildInboxCard(
                            palette,
                            inboxCount,
                            urgent,
                            sourceCounts,
                            _unreadNotifications,
                          ),
                        ),
                        const SizedBox(width: 9),
                        Expanded(child: _buildBriefCard(palette)),
                      ],
                    ),
                    const SizedBox(height: 9),
                    _buildFilesCard(palette),
                    if (_loading) ...[
                      const SizedBox(height: 14),
                      LinearProgressIndicator(
                        color: palette.primary,
                        backgroundColor: palette.primarySoft,
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeroChat(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [palette.primaryLight, palette.primary],
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: palette.primary.withValues(alpha: 0.24),
            blurRadius: 22,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            right: -30,
            top: -38,
            child: Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.14),
                shape: BoxShape.circle,
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 5,
                    height: 5,
                    decoration: const BoxDecoration(
                      color: Color(0xFFD8FFE8),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    'AI 助手 · 在线',
                    style: TextStyle(
                      fontSize: 9,
                      letterSpacing: 1,
                      fontWeight: FontWeight.w700,
                      color: Colors.white.withValues(alpha: 0.82),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              const Text(
                '今天想先处理什么？',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _chatController,
                textInputAction: TextInputAction.send,
                onSubmitted: _ask,
                style: const TextStyle(fontSize: 13, color: Colors.white),
                decoration: InputDecoration(
                  hintText: '问点什么，或让我处理一件事…',
                  hintStyle: TextStyle(
                    color: Colors.white.withValues(alpha: 0.82),
                    fontSize: 12,
                  ),
                  filled: true,
                  fillColor: Colors.white.withValues(alpha: 0.16),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 10,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.24),
                    ),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.24),
                    ),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.55),
                    ),
                  ),
                  suffixIcon: IconButton(
                    onPressed: () => _ask(_chatController.text),
                    icon: const Icon(
                      Icons.arrow_forward_rounded,
                      size: 17,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 5,
                runSpacing: 5,
                children: [
                  for (final prompt in const [
                    '整理收件箱',
                    '准备 10:30 会议',
                    '写周报',
                  ])
                    InkWell(
                      onTap: () => _ask(prompt),
                      borderRadius: BorderRadius.circular(20),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 9,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.18),
                          ),
                        ),
                        child: Text(
                          prompt,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Colors.white.withValues(alpha: 0.9),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTodayCard(AppPalette palette) {
    final activeEvents =
        _events.where((event) => !eventHasEnded(event)).toList();
    final events = activeEvents.take(2).toList();
    final allEnded = _events.isNotEmpty && activeEvents.isEmpty;
    return AppCard(
      child: Column(
        children: [
          Row(
            children: [
              Text(
                '今天',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w700,
                  color: palette.muted,
                ),
              ),
              const Spacer(),
              _LinkLabel(
                label: '查看日程',
                onTap: () => _pushAndRefresh(const ScheduleScreen()),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (events.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Icon(Icons.event_available_outlined, size: 16, color: palette.muted),
                  const SizedBox(width: 6),
                  Text(
                    allEnded
                        ? '今天的日程已结束。'
                        : '今天没有日程，适合推进长期任务。',
                    style: TextStyle(fontSize: 11.5, color: palette.muted),
                  ),
                ],
              ),
            )
          else
            for (final event in events)
              _TimelineRow(
                time: _eventTime(event),
                title: (event['title'] ?? '日程').toString(),
                subtitle: (event['notes'] ?? '').toString(),
                accent: events.indexOf(event) == 0,
              ),
          if (_dueToday > 0 || _overdue > 0) ...[
            const SizedBox(height: 7),
            Divider(color: palette.line),
            const SizedBox(height: 6),
            InkWell(
              onTap: () => _pushAndRefresh(const TodoScreen()),
              child: Row(
                children: [
                  TagDot(color: palette.accent),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(
                      _overdue > 0
                          ? '$_dueToday 项待办今天到期 · $_overdue 项已逾期'
                          : '$_dueToday 项待办今天到期',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: palette.accent,
                      ),
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, size: 16, color: palette.muted),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildInboxCard(
    AppPalette palette,
    int total,
    int urgent,
    Map<String, int> sourceCounts,
    int notificationCount,
  ) {
    return AppCard(
      onTap: () => _pushAndRefresh(const InboxScreen()),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '信息',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w700,
                  color: palette.muted,
                ),
              ),
              const Spacer(),
              Icon(Icons.chevron_right_rounded, size: 16, color: palette.muted),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '$total',
                style: TextStyle(
                  fontSize: 26,
                  height: 1,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1,
                  color: palette.ink,
                ),
              ),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(
                  '待处理',
                  style: TextStyle(fontSize: 10, color: palette.muted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              SourcePill(
                label: '邮件 ${sourceCounts['mail'] ?? 0}',
                color: palette.primary,
                icon: Icons.mail_outline_rounded,
              ),
              SourcePill(
                label: '钉钉 ${sourceCounts['dingtalk'] ?? 0}',
                color: palette.accent,
                icon: Icons.chat_outlined,
              ),
              if (notificationCount > 0)
                SourcePill(
                  label: '通知 $notificationCount',
                  color: palette.success,
                  icon: Icons.notifications_none_rounded,
                ),
            ],
          ),
          if (urgent > 0) ...[
            const SizedBox(height: 7),
            Row(
              children: [
                TagDot(color: palette.accent),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    '$urgent 条紧急',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: palette.accent,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildBriefCard(AppPalette palette) {
    final summary = _brief?.summary ?? '';
    return AppCard(
      color: palette.primarySoft,
      borderColor: Colors.transparent,
      onTap: () => _pushAndRefresh(const BriefScreen()),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                _botName.isEmpty ? '今日简报' : '今日简报 · $_botName',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w700,
                  color: palette.primary,
                ),
              ),
              const Spacer(),
              Icon(Icons.auto_awesome, size: 14, color: palette.primary),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            summary.isEmpty ? '还没有生成今日简报。' : summary,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 11.5,
              height: 1.6,
              color: palette.ink.withValues(alpha: 0.82),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '查看今日简报 →',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              color: palette.primary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilesCard(AppPalette palette) {
    final file = _files.isEmpty ? null : _files.first;
    return AppCard(
      onTap: () => _pushAndRefresh(const LibraryScreen()),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: palette.primarySoft,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(Icons.folder_outlined, size: 16, color: palette.primary),
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '文件与笔记',
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1,
                    fontWeight: FontWeight.w700,
                    color: palette.muted,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  file?.originalName ?? '还没有最近文件',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: palette.ink,
                  ),
                ),
              ],
            ),
          ),
          Text(
            '进入',
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: palette.primary,
            ),
          ),
          Icon(Icons.chevron_right_rounded, size: 16, color: palette.muted),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final initial = name.isEmpty ? '我' : name.characters.first;
    return Container(
      width: 36,
      height: 36,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [palette.accent.withValues(alpha: 0.55), palette.accent],
        ),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        initial,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w800,
          color: Colors.white,
        ),
      ),
    );
  }
}

class _LinkLabel extends StatelessWidget {
  const _LinkLabel({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 1),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 10.5,
            fontWeight: FontWeight.w700,
            color: palette.primary,
          ),
        ),
      ),
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.time,
    required this.title,
    required this.subtitle,
    this.accent = false,
  });

  final String time;
  final String title;
  final String subtitle;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 36,
            child: Text(
              time,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: palette.ink,
              ),
            ),
          ),
          Container(
            width: 2,
            height: 28,
            margin: const EdgeInsets.only(right: 8),
            decoration: BoxDecoration(
              color: accent ? palette.accent : palette.line,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: palette.ink,
                  ),
                ),
                if (subtitle.isNotEmpty)
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
