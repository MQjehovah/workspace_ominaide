import 'package:flutter/material.dart';

import '../models/cos_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'mail_screen.dart';
import 'schedule_screen.dart';
import 'todo_screen.dart';

class InboxScreen extends StatefulWidget {
  const InboxScreen({super.key, this.initialFilter = 'all'});

  final String initialFilter;

  @override
  State<InboxScreen> createState() => _InboxScreenState();
}

class _InboxScreenState extends State<InboxScreen> {
  late String _filter = widget.initialFilter;
  List<TriageItem> _items = [];
  bool _loading = true;

  static const _filters = [
    ('all', '全部'),
    ('mail', '邮件'),
    ('dingtalk', '钉钉'),
    ('notification', '通知'),
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final api = ApiService();
    TriageSnapshot? triage;
    List<Map<String, dynamic>> notifications = [];
    try {
      triage = await api.getTriage();
    } catch (_) {}
    try {
      notifications = await api.listNotifications(limit: 50);
    } catch (_) {}
    if (!mounted) return;
    final items = <TriageItem>[];
    if (triage != null) {
      for (final key in const ['urgent', 'needs_reply', 'today', 'fyi']) {
        items.addAll(triage.groups[key] ?? const []);
      }
    }
    for (final n in notifications) {
      if (n['read'] == true) continue;
      final id = n['id'];
      items.add(TriageItem(
        id: 'notification:$id',
        source: 'notification',
        title: (n['title'] ?? '通知').toString(),
        summary: (n['body'] ?? '').toString(),
        from: '通知',
        priority: 'needs_reply',
        needsReply: true,
        time: DateTime.tryParse('${n['created_at'] ?? ''}'),
      ));
    }
    setState(() {
      _items = items;
      _loading = false;
    });
  }

  List<TriageItem> get _visible {
    if (_filter == 'all') return _items;
    return _items.where((item) => item.source == _filter).toList();
  }

  Future<void> _open(TriageItem item) async {
    if (item.source == 'mail' && item.sourceId != null) {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => MailScreen(detailId: item.sourceId)),
      );
      if (mounted) _load();
      return;
    }
    if (item.source == 'todo') {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const TodoScreen()),
      );
      return;
    }
    if (item.source == 'schedule') {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const ScheduleScreen()),
      );
      return;
    }
    if (item.source == 'notification' && item.id.startsWith('notification:')) {
      final id = int.tryParse(item.id.split(':').last);
      if (id != null) {
        await ApiService().markNotificationRead(id);
      }
    }
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (context) {
        final palette = AppPalette.of(context);
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  item.title,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
                if (item.summary.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    item.summary,
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.7,
                      color: palette.muted,
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
    if (mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Inbox',
              title: '收件箱',
              subtitle: '${_visible.length} 条待处理',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.done_all_rounded,
                  tooltip: '全部已读',
                  onTap: () async {
                    await ApiService().markNotificationsRead();
                    await _load();
                  },
                ),
              ],
            ),
            SizedBox(
              height: 36,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                itemCount: _filters.length,
                separatorBuilder: (_, __) => const SizedBox(width: 6),
                itemBuilder: (context, index) {
                  final filter = _filters[index];
                  final selected = _filter == filter.$1;
                  return InkWell(
                    onTap: () => setState(() => _filter = filter.$1),
                    borderRadius: BorderRadius.circular(18),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 13,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: selected ? palette.primary : palette.card,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(
                          color: selected ? palette.primary : palette.line,
                        ),
                      ),
                      child: Text(
                        filter.$2,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: selected ? Colors.white : palette.muted,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _visible.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: const [
                                SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.inbox_outlined,
                                  title: '这里很干净',
                                  subtitle: '没有需要处理的消息。',
                                ),
                              ],
                            )
                          : ListView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              itemCount: _visible.length,
                              itemBuilder: (context, index) {
                                return _InboxRow(
                                  item: _visible[index],
                                  onTap: () => _open(_visible[index]),
                                );
                              },
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InboxRow extends StatelessWidget {
  const _InboxRow({required this.item, required this.onTap});

  final TriageItem item;
  final VoidCallback onTap;

  (IconData, Color) get _visual {
    switch (item.source) {
      case 'mail':
        return (Icons.mail_outline_rounded, const Color(0xFF2E7CF6));
      case 'dingtalk':
        return (Icons.chat_outlined, const Color(0xFFF97316));
      case 'notification':
        return (Icons.notifications_none_rounded, const Color(0xFF0FA97A));
      case 'rss':
        return (Icons.rss_feed_rounded, const Color(0xFF7C5CF6));
      case 'todo':
        return (Icons.check_circle_outline_rounded, const Color(0xFFF97316));
      case 'schedule':
        return (Icons.event_outlined, const Color(0xFF2E7CF6));
      default:
        return (Icons.circle_outlined, const Color(0xFF6F7D92));
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final (icon, color) = _visual;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.11),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 16, color: color),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12.5,
                            fontWeight: item.needsReply
                                ? FontWeight.w800
                                : FontWeight.w600,
                            color: palette.ink,
                          ),
                        ),
                      ),
                      if (item.isUrgent)
                        Container(
                          margin: const EdgeInsets.only(left: 6),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 5,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: palette.accent.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            '紧急',
                            style: TextStyle(
                              fontSize: 8,
                              fontWeight: FontWeight.w800,
                              color: palette.accent,
                            ),
                          ),
                        ),
                    ],
                  ),
                  if (item.summary.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      item.summary,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10.5,
                        height: 1.5,
                        color: palette.muted,
                      ),
                    ),
                  ],
                  const SizedBox(height: 4),
                  Text(
                    [
                      if (item.from.isNotEmpty) item.from,
                      if (item.time != null)
                        '${item.time!.toLocal().month}/${item.time!.toLocal().day} '
                            '${item.time!.toLocal().hour.toString().padLeft(2, '0')}:'
                            '${item.time!.toLocal().minute.toString().padLeft(2, '0')}',
                    ].join(' · '),
                    style: TextStyle(fontSize: 9, color: palette.muted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
