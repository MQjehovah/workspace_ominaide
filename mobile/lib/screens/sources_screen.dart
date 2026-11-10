import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class SourcesScreen extends StatefulWidget {
  const SourcesScreen({super.key});

  @override
  State<SourcesScreen> createState() => _SourcesScreenState();
}

class _SourcesScreenState extends State<SourcesScreen> {
  List<Map<String, dynamic>> _entries = [];
  bool _loading = true;
  bool _error = false;

  int get _unreadCount =>
      _entries.where((entry) => entry['read'] == false).length;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = false;
    });
    List<Map<String, dynamic>> entries = [];
    try {
      entries = await ApiService().listSourceItems();
    } catch (_) {
      if (mounted) setState(() => _error = true);
    }
    if (!mounted) return;
    setState(() {
      _entries = entries;
      _loading = false;
    });
  }

  Future<void> _markAllRead() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final updated = await ApiService().markAllSourceItemsRead();
      if (!mounted) return;
      setState(() {
        for (final entry in _entries) {
          entry['read'] = true;
        }
      });
      messenger.showSnackBar(
        SnackBar(
          content: Text(updated > 0 ? '已标记 $updated 条为已读' : '没有未读资讯'),
        ),
      );
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(content: Text('操作失败，请稍后重试')),
      );
    }
  }

  Future<void> _open(Map<String, dynamic> entry) async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  (entry['title'] ?? '').toString(),
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  (entry['summary'] ?? entry['content'] ?? '').toString(),
                  maxLines: 8,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12.5,
                    height: 1.7,
                    color: palette.muted,
                  ),
                ),
                if ((entry['link'] ?? '').toString().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    (entry['link'] ?? '').toString(),
                    style: TextStyle(fontSize: 10, color: palette.primary),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
    final id = entry['id'];
    if (id is int) {
      try {
        await ApiService().put('/sources/items/$id/read', const {});
      } catch (_) {
        // Badge refresh is best-effort; keep the UI usable offline.
      }
      if (mounted) setState(() => entry['read'] = true);
    }
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
              kicker: 'Sources',
              title: '资讯',
              subtitle: _unreadCount > 0
                  ? '$_unreadCount 条未读 · ${_entries.length} 条最近更新'
                  : '${_entries.length} 条最近更新',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                if (_unreadCount > 0) ...[
                  const SizedBox(width: 6),
                  RoundIconButton(
                    icon: Icons.done_all_rounded,
                    tooltip: '全部已读',
                    onTap: _markAllRead,
                  ),
                ],
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: _load,
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _error
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                ErrorState(onRetry: _load),
                              ],
                            )
                          : _entries.isEmpty
                              ? ListView(
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  children: const [
                                    SizedBox(height: 50),
                                    EmptyState(
                                      icon: Icons.rss_feed_rounded,
                                      title: '还没有内容',
                                      subtitle: '在 Web 端添加资讯源后，内容会同步到这里。',
                                    ),
                                  ],
                                )
                              : ListView.builder(
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  padding:
                                      const EdgeInsets.fromLTRB(16, 0, 16, 20),
                                  itemCount: _entries.length,
                                  itemBuilder: (context, index) {
                                    final entry = _entries[index];
                                    return Padding(
                                      padding: const EdgeInsets.only(bottom: 8),
                                      child: AppCard(
                                        onTap: () => _open(entry),
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              (entry['title'] ?? '').toString(),
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(
                                                fontSize: 13,
                                                fontWeight: FontWeight.w700,
                                                color: palette.ink,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              (entry['summary'] ??
                                                      entry['content'] ??
                                                      '')
                                                  .toString(),
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(
                                                fontSize: 10.5,
                                                height: 1.5,
                                                color: palette.muted,
                                              ),
                                            ),
                                            const SizedBox(height: 5),
                                            Row(
                                              children: [
                                                if (entry['read'] == false) ...[
                                                  Container(
                                                    width: 6,
                                                    height: 6,
                                                    decoration: BoxDecoration(
                                                      color: palette.primary,
                                                      shape: BoxShape.circle,
                                                    ),
                                                  ),
                                                  const SizedBox(width: 5),
                                                ],
                                                Expanded(
                                                  child: Text(
                                                    (entry['source_title'] ??
                                                            '资讯')
                                                        .toString(),
                                                    style: TextStyle(
                                                      fontSize: 9.5,
                                                      fontWeight:
                                                          FontWeight.w700,
                                                      color: palette.primary,
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),
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
