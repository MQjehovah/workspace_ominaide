import 'dart:async';

import 'package:flutter/material.dart';

import '../models/chat_session.dart';
import '../models/brief_models.dart';
import '../models/file_item.dart';
import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../services/brief_repository.dart';
import '../services/event_time.dart';
import '../services/local_cache_service.dart';
import '../services/refresh_bus.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'brief_screen.dart';
import 'chat_screen.dart';
import 'files_screen.dart';
import 'library_screen.dart';
import 'notes_screen.dart';
import 'projects_screen.dart';
import 'quick_capture_screen.dart';
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
  List<Map<String, dynamic>> _events = [];
  List<Map<String, dynamic>> _todos = [];
  List<Map<String, dynamic>> _proposals = [];
  List<FileItem> _files = [];
  List<Map<String, dynamic>> _notes = [];
  List<Map<String, dynamic>> _projects = [];
  List<String> _suggestions = const [
    '整理收件箱',
    '看看今天的待办',
    '写本周周报',
  ];
  String _name = '';
  bool _loading = true;
  bool _briefLoading = true;
  bool _error = false;
  int _loadToken = 0;
  DateTime? _lastLoadAt;
  late final ValueNotifier<int> _refresh = RefreshBus.signal('workbench');

  @override
  void initState() {
    super.initState();
    _refresh.addListener(_onRefreshSignal);
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    // Show last good data immediately, then refresh from the network.
    await _loadLocalCache();
    if (mounted) await _load();
  }

  void _onRefreshSignal() {
    if (mounted) _load();
  }

  @override
  void dispose() {
    _refresh.removeListener(_onRefreshSignal);
    _chatController.dispose();
    super.dispose();
  }

  Future<T?> _safe<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  Future<void> _loadLocalCache() async {
    final results = await Future.wait<Map<String, dynamic>?>([
      LocalCacheService().readJson('workbench.summary'),
      LocalCacheService().readJson('workbench.brief'),
    ]);
    if (!mounted) return;
    final summary = results[0];
    final brief = results[1];
    setState(() {
      if (summary != null) _applySummary(summary);
      if (brief != null) _brief = DailyBrief.fromJson(brief);
    });
  }

  void _applySummary(Map<String, dynamic> summary) {
    final recent = (summary['recent'] as Map?) ?? const {};
    final recentFiles = (recent['files'] as List?) ?? const [];
    final recentNotes = (recent['notes'] as List?) ?? const [];
    final recentProjects = (recent['projects'] as List?) ?? const [];
    _events = ((summary['events'] as List?) ?? const [])
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    _todos = ((summary['todos'] as List?) ?? const [])
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    _files = recentFiles
        .whereType<Map>()
        .map((e) => FileItem.fromJson(
              e.map((k, v) => MapEntry(k.toString(), v)),
            ))
        .toList();
    _notes = recentNotes
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    _projects = recentProjects
        .whereType<Map>()
        .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
  }

  Future<void> _load({bool force = false}) async {
    if (!force &&
        _lastLoadAt != null &&
        DateTime.now().difference(_lastLoadAt!) < const Duration(seconds: 5)) {
      return;
    }
    _lastLoadAt = DateTime.now();
    final token = ++_loadToken;
    await BotSelectionService().load();
    final api = ApiService();
    // The backend serves the daily brief from its hourly cache, so start it in
    // parallel; it still never blocks the first paint.
    final briefFuture = _safe(briefRepository.getDailyBrief(force: force));

    // Fast, cheap calls first: these unblock the whole workbench.
    final results = await Future.wait<dynamic>([
      _safe(api.getWorkbenchSummary()),
      _safe(api.getMe()),
      _safe(api.getProposals()),
    ]);
    if (!mounted || token != _loadToken) return;

    var summary = (results[0] as Map<String, dynamic>?) ?? <String, dynamic>{};
    if (summary.isEmpty) {
      final cached = await LocalCacheService().readJson('workbench.summary');
      if (cached != null && token == _loadToken) summary = cached;
    } else {
      await LocalCacheService().writeJson('workbench.summary', summary);
    }
    if (!mounted || token != _loadToken) return;

    final me = results[1] as Map<String, dynamic>?;
    final proposals =
        (results[2] as List<Map<String, dynamic>>?) ?? const [];
    setState(() {
      _error = results[0] == null && summary.isEmpty;
      _applySummary(summary);
      _proposals = proposals;
      _name = (me?['display_name'] ?? me?['username'] ?? '').toString();
      _loading = false;
      _briefLoading = true;
    });

    // The daily brief is served from the backend's hourly snapshot. Its
    // prompts are the workbench suggestion chips; there is no separate call.
    final brief = await briefFuture;
    if (!mounted || token != _loadToken) return;
    setState(() {
      _briefLoading = false;
      if (brief != null) {
        _brief = brief;
        if (brief.prompts.isNotEmpty) {
          _suggestions = brief.prompts;
        }
      }
    });
    if (brief != null) {
      unawaited(LocalCacheService().writeJson('workbench.brief', {
        'day': brief.day,
        'summary': brief.summary,
        'prompts': brief.prompts,
      }));
    }
  }

  Future<void> _acceptProposal(Map<String, dynamic> item) async {
    final id = item['id'];
    if (id is! int) return;
    try {
      final action = item['primary_action'];
      final hasAction = action is Map && action['kind'] == 'create_todo';
      final ok = await ApiService().actProposal(id, hasAction ? 'execute' : 'accept');
      if (!ok) throw Exception('处理失败');
      if (!mounted) return;
      setState(() {
        _proposals =
            _proposals.where((e) => e['id'] != id).toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已处理提案')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('处理提案失败: $e')),
      );
    }
  }

  Future<void> _dismissProposal(Map<String, dynamic> item) async {
    final id = item['id'];
    if (id is! int) return;
    try {
      await ApiService().actProposal(id, 'dismiss');
      if (!mounted) return;
      setState(() {
        _proposals =
            _proposals.where((e) => e['id'] != id).toList();
      });
    } catch (_) {
      // Keep the item when the request fails.
    }
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
    if (mounted) _load();
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
    final end =
        DateTime(now.year, now.month, now.day).add(const Duration(days: 1));
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
    final parsed = eventStart(event);
    if (parsed == null) return '';
    return '${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            await _load(force: true);
          },
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
                    icon: Icons.add_rounded,
                    tooltip: '随手记',
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const QuickCaptureScreen()),
                    ),
                  ),
                  const SizedBox(width: 6),
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
              if (_loading)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(2),
                    child: LinearProgressIndicator(
                      minHeight: 3,
                      color: palette.primary,
                      backgroundColor: palette.primarySoft,
                    ),
                  ),
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
                    _buildProposalsCard(palette),
                    const SizedBox(height: 9),
                    _buildRecentCard(palette),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String get _briefSummary {
    final summary = (_brief?.summary ?? '').trim();
    if (summary.isNotEmpty) return summary;
    return _briefLoading ? '正在生成今日简报…' : '今天没有需要特别处理的事项。';
  }

  Widget _buildHeroChat(AppPalette palette) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _pushAndRefresh(const BriefScreen()),
      child: Container(
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
                    Icon(
                      Icons.auto_awesome,
                      size: 14,
                      color: Colors.white.withValues(alpha: 0.95),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      '今日简报',
                      style: TextStyle(
                        fontSize: 11,
                        letterSpacing: 0.5,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  _briefSummary,
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 11.5,
                    height: 1.6,
                    color: Colors.white.withValues(alpha: 0.94),
                  ),
                ),
                const SizedBox(height: 8),
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
                SizedBox(
                  height: 28,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: _suggestions.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 5),
                    itemBuilder: (context, index) {
                      final prompt = _suggestions[index];
                      return InkWell(
                        onTap: () => _ask(prompt),
                        borderRadius: BorderRadius.circular(20),
                        child: Container(
                          constraints: const BoxConstraints(maxWidth: 250),
                          padding: const EdgeInsets.symmetric(horizontal: 10),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.18),
                            ),
                          ),
                          child: Center(
                            widthFactor: 1,
                            heightFactor: 1,
                            child: Text(
                              prompt,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: Colors.white.withValues(alpha: 0.9),
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
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
                  Icon(Icons.event_available_outlined,
                      size: 16, color: palette.muted),
                  const SizedBox(width: 6),
                  Text(
                    allEnded ? '今天的日程已结束。' : '今天没有日程，适合推进长期任务。',
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
                  Icon(Icons.chevron_right_rounded,
                      size: 16, color: palette.muted),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<_RecentEntry> _recentEntries(AppPalette palette) {
    final entries = <_RecentEntry>[];
    for (final note in _notes) {
      if (note['is_folder'] == true) continue;
      final title = (note['title'] ?? '').toString().trim();
      if (title.isEmpty) continue;
      entries.add(
        _RecentEntry(
          title: title,
          type: '笔记',
          icon: Icons.article_outlined,
          color: palette.success,
          time: DateTime.tryParse(
            '${note['updated_at'] ?? note['created_at'] ?? ''}',
          ),
          page: const NotesScreen(),
        ),
      );
    }
    for (final file in _files) {
      if (file.isFolder) continue;
      entries.add(
        _RecentEntry(
          title: file.originalName,
          type: '文件',
          icon: Icons.insert_drive_file_outlined,
          color: palette.primary,
          time: DateTime.tryParse(file.createdAt),
          page: const FilesScreen(),
        ),
      );
    }
    for (final project in _projects) {
      final title = (project['name'] ?? '').toString().trim();
      if (title.isEmpty) continue;
      entries.add(
        _RecentEntry(
          title: title,
          type: '项目',
          icon: Icons.grid_view_outlined,
          color: const Color(0xFF7C5CF6),
          time: DateTime.tryParse(
            '${project['updated_at'] ?? project['created_at'] ?? ''}',
          ),
          page: const ProjectsScreen(),
        ),
      );
    }
    entries.sort((a, b) {
      final left = a.time;
      final right = b.time;
      if (left == null && right == null) return 0;
      if (left == null) return 1;
      if (right == null) return -1;
      return right.compareTo(left);
    });
    return entries.take(3).toList();
  }

  String _suggestionKindLabel(String kind) {
    switch (kind) {
      case 'prepare':
        return '准备';
      case 'reply':
        return '回复';
      case 'todo':
        return '待办';
      case 'schedule':
        return '日程';
      case 'review':
        return '复盘';
      default:
        return '跟进';
    }
  }

  IconData _suggestionKindIcon(String kind) {
    switch (kind) {
      case 'prepare':
        return Icons.event_available_rounded;
      case 'reply':
        return Icons.reply_rounded;
      case 'todo':
        return Icons.check_circle_outline_rounded;
      case 'schedule':
        return Icons.calendar_month_rounded;
      case 'review':
        return Icons.rate_review_outlined;
      default:
        return Icons.auto_awesome_rounded;
    }
  }

  Color _suggestionKindColor(AppPalette palette, String kind) {
    switch (kind) {
      case 'reply':
      case 'review':
        return palette.success;
      case 'todo':
        return palette.accent;
      default:
        return palette.primary;
    }
  }

  bool _suggestionHasAction(Map<String, dynamic> item) {
    final action = item['primary_action'];
    return action is Map && action['kind'] == 'create_todo';
  }

  Future<void> _showActivityActions(Map<String, dynamic> item) async {
    final palette = AppPalette.of(context);
    final hasAction = _suggestionHasAction(item);
    final title = (item['title'] ?? '').toString();
    final reason = (item['reason'] ?? '').toString();
    final choice = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (sheetContext) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: palette.ink,
                      ),
                    ),
                    if (reason.isNotEmpty) ...[
                      const SizedBox(height: 5),
                      Text(
                        reason,
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.5,
                          color: palette.muted,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              ListTile(
                leading: Icon(
                  hasAction ? Icons.playlist_add_check_rounded : Icons.add_task_rounded,
                  color: palette.primary,
                ),
                title: Text(hasAction ? '执行建议' : '创建待办'),
                subtitle: Text(
                  hasAction ? '按建议创建一个待办' : '把这条建议转成待办',
                  style: TextStyle(fontSize: 11, color: palette.muted),
                ),
                onTap: () => Navigator.pop(sheetContext, 'primary'),
              ),
              ListTile(
                leading: Icon(Icons.close_rounded, color: palette.muted),
                title: Text('忽略', style: TextStyle(color: palette.muted)),
                onTap: () => Navigator.pop(sheetContext, 'dismiss'),
              ),
              const SizedBox(height: 6),
            ],
          ),
        );
      },
    );
    if (!mounted || choice == null) return;
    if (choice == 'primary') {
      await _acceptProposal(item);
    } else if (choice == 'dismiss') {
      await _dismissProposal(item);
    }
  }

  Widget _proposalCard(AppPalette palette, Map<String, dynamic> item) {
    final kind = (item['kind'] ?? 'follow_up').toString();
    final title = (item['title'] ?? '').toString();
    final reason = (item['reason'] ?? '').toString();
    final confidence = (item['confidence'] as num?)?.toDouble() ?? 0.5;
    final color = _suggestionKindColor(palette, kind);
    final hasAction = _suggestionHasAction(item);
    return GestureDetector(
        onTap: () => _showActivityActions(item),
        child: AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 7,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(_suggestionKindIcon(kind), size: 11, color: color),
                        const SizedBox(width: 4),
                        Text(
                          _suggestionKindLabel(kind),
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: color,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  Text(
                    confidence >= 0.75
                        ? '高置信建议'
                        : confidence >= 0.55
                            ? '值得处理'
                            : '参考建议',
                    style: TextStyle(fontSize: 9.5, color: palette.muted),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                title,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.35,
                  fontWeight: FontWeight.w700,
                  color: palette.ink,
                ),
              ),
              if (reason.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  reason,
                  style: TextStyle(
                    fontSize: 11.5,
                    height: 1.55,
                    color: palette.muted,
                  ),
                ),
              ],
              const SizedBox(height: 9),
              Row(
                children: [
                  Icon(
                    hasAction
                        ? Icons.playlist_add_check_rounded
                        : Icons.add_task_rounded,
                    size: 13,
                    color: hasAction ? color : palette.muted,
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      hasAction ? '可一键执行：创建待办' : '可转为待办继续跟进',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10.5,
                        color: hasAction ? color : palette.muted,
                      ),
                    ),
                  ),
                  Text(
                    '点击处理',
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
                  const SizedBox(width: 2),
                  Icon(Icons.chevron_right_rounded,
                      size: 15, color: palette.muted),
                ],
              ),
            ],
          ),
        ),
      );
  }

  Widget _buildProposalsCard(AppPalette palette) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2),
          child: Row(
            children: [
              Icon(Icons.auto_awesome_rounded, size: 16, color: palette.primary),
              const SizedBox(width: 6),
              Text(
                '活动分析',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const Spacer(),
              if (_proposals.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: palette.primarySoft,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${_proposals.length} 条',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: palette.primary,
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 2),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2),
          child: Text(
            '根据日程、邮件、钉钉和近期活动预判接下来要做的事',
            style: TextStyle(fontSize: 10.5, color: palette.muted),
          ),
        ),
        const SizedBox(height: 8),
        if (_proposals.isEmpty)
          AppCard(
            child: Row(
              children: [
                Icon(Icons.insights_rounded, size: 18, color: palette.muted),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '暂时没有新的分析结果，系统每小时自动更新。',
                    style: TextStyle(fontSize: 11.5, color: palette.muted),
                  ),
                ),
              ],
            ),
          )
        else
          for (final item in _proposals.take(6))
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _proposalCard(palette, item),
            ),
      ],
    );
  }

  Widget _buildRecentCard(AppPalette palette) {
    final entries = _recentEntries(palette);
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '最近使用',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1,
                  fontWeight: FontWeight.w700,
                  color: palette.muted,
                ),
              ),
              const Spacer(),
              InkWell(
                onTap: () => _pushAndRefresh(const LibraryScreen()),
                borderRadius: BorderRadius.circular(6),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '全部',
                      style: TextStyle(
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                        color: palette.primary,
                      ),
                    ),
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 16,
                      color: palette.primary,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 5),
          if (entries.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Text(
                '最近还没有使用记录，上传文件或记一条笔记后会出现在这里。',
                style: TextStyle(fontSize: 11, color: palette.muted),
              ),
            )
          else
            for (var i = 0; i < entries.length; i++) ...[
              if (i > 0)
                Divider(height: 12, color: palette.line.withValues(alpha: 0.8)),
              InkWell(
                onTap: () => _pushAndRefresh(entries[i].page),
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Container(
                        width: 30,
                        height: 30,
                        decoration: BoxDecoration(
                          color: entries[i].color.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(9),
                        ),
                        child: Icon(
                          entries[i].icon,
                          size: 15,
                          color: entries[i].color,
                        ),
                      ),
                      const SizedBox(width: 9),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              entries[i].title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: palette.ink,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${entries[i].type} · ${relativeTimeLabel(entries[i].time)}',
                              style: TextStyle(
                                fontSize: 9.5,
                                color: palette.muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Icon(
                        Icons.chevron_right_rounded,
                        size: 16,
                        color: palette.muted,
                      ),
                    ],
                  ),
                ),
              ),
            ],
        ],
      ),
    );
  }
}

class _RecentEntry {
  const _RecentEntry({
    required this.title,
    required this.type,
    required this.icon,
    required this.color,
    required this.page,
    this.time,
  });

  final String title;
  final String type;
  final IconData icon;
  final Color color;
  final Widget page;
  final DateTime? time;
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
