import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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

  String _htmlToText(String html) {
    if (html.trim().isEmpty) return '';
    var text = html
        .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
        .replaceAll(RegExp(r'</p\s*>', caseSensitive: false), '\n\n')
        .replaceAll(RegExp(r'</div\s*>', caseSensitive: false), '\n')
        .replaceAll(RegExp(r'</h[1-6]\s*>', caseSensitive: false), '\n\n')
        .replaceAll(RegExp(r'<li[^>]*>', caseSensitive: false), '• ')
        .replaceAll(RegExp(r'</li\s*>', caseSensitive: false), '\n')
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&#x27;', "'")
        .replaceAll('&ldquo;', '“')
        .replaceAll('&rdquo;', '”')
        .replaceAll('&mdash;', '—')
        .replaceAll('&hellip;', '…');
    text = text.replaceAllMapped(RegExp(r'&#(x?[0-9a-fA-F]+);'), (match) {
      final raw = match.group(1) ?? '';
      try {
        final code = raw.startsWith('x') || raw.startsWith('X')
            ? int.parse(raw.substring(1), radix: 16)
            : int.parse(raw);
        return String.fromCharCode(code);
      } catch (_) {
        return match.group(0) ?? '';
      }
    });
    return text.replaceAll(RegExp(r'\n{3,}'), '\n\n').trim();
  }

  String _articleText(Map<String, dynamic> entry) {
    final content = (entry['content'] ?? '').toString().trim();
    final summary = (entry['summary'] ?? '').toString().trim();
    return _htmlToText(content.isNotEmpty ? content : summary);
  }

  String _formatPublished(dynamic value) {
    final text = (value ?? '').toString().trim();
    if (text.isEmpty) return '';
    final parsed = DateTime.tryParse(text);
    if (parsed == null) return text;
    final local = parsed.toLocal();
    String two(int value) => value.toString().padLeft(2, '0');
    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  Future<void> _openLink(String link) async {
    final uri = Uri.tryParse(link);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('无法打开链接')),
      );
    }
  }

  Future<void> _open(Map<String, dynamic> entry) async {
    final palette = AppPalette.of(context);
    final title = (entry['title'] ?? '').toString();
    final sourceTitle = (entry['source_title'] ?? '资讯').toString();
    final published = _formatPublished(entry['published']);
    final link = (entry['link'] ?? '').toString().trim();
    final body = _articleText(entry);

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (context) {
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.9,
          minChildSize: 0.45,
          maxChildSize: 0.96,
          builder: (context, controller) {
            return ListView(
              controller: controller,
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 18,
                    height: 1.45,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        published.isEmpty
                            ? sourceTitle
                            : '$sourceTitle · $published',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: palette.primary,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Divider(color: palette.line),
                const SizedBox(height: 10),
                SelectableText(
                  body.isEmpty ? '暂无正文，可打开原文查看。' : body,
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.85,
                    color: palette.ink,
                  ),
                ),
                if (link.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  OutlinedButton.icon(
                    onPressed: () => _openLink(link),
                    icon: const Icon(Icons.open_in_new_rounded, size: 18),
                    label: const Text('在浏览器打开原文'),
                  ),
                ],
              ],
            );
          },
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
