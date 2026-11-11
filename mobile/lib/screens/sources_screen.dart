import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/article_image.dart';

class SourcesScreen extends StatefulWidget {
  const SourcesScreen({super.key});

  @override
  State<SourcesScreen> createState() => _SourcesScreenState();
}

class _SourcesScreenState extends State<SourcesScreen> {
  List<Map<String, dynamic>> _entries = [];
  bool _loading = true;
  bool _error = false;
  bool _onlyUnread = false;

  int get _unreadCount =>
      _entries.where((entry) => entry['read'] == false).length;

  List<Map<String, dynamic>> get _visible => _onlyUnread
      ? _entries.where((entry) => entry['read'] == false).toList()
      : _entries;

  String _preview(Map<String, dynamic> entry) {
    final raw = (entry['summary'] ?? entry['content'] ?? '').toString();
    if (raw.trim().isEmpty) return '';
    var text = raw
        .replaceAll(
          RegExp(r'<(script|style)[^>]*>[\s\S]*?</\1>', caseSensitive: false),
          ' ',
        )
        .replaceAll(RegExp(r'<[^>]+>'), ' ')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&ldquo;', '“')
        .replaceAll('&rdquo;', '”')
        .replaceAll('&mdash;', '—')
        .replaceAll('&hellip;', '…');
    text = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (text.length > 120) text = '${text.substring(0, 120)}…';
    return text;
  }

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

  String? _htmlAttr(String tag, List<String> names) {
    for (final name in names) {
      final match = RegExp(
        '$name\\s*=\\s*["\']([^"\']*)["\']',
        caseSensitive: false,
      ).firstMatch(tag);
      final value = match?.group(1)?.trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

  String _resolveImageUrl(String src, String baseUrl) {
    final value = src.trim();
    if (value.startsWith('//')) return 'https:$value';
    if (value.startsWith('data:')) return value;
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    final base = Uri.tryParse(baseUrl);
    if (base != null) {
      try {
        return base.resolve(value).toString();
      } catch (_) {
        // Keep the original value.
      }
    }
    return value;
  }

  /// The IT Home CDN negotiates WebP/AVIF from the `Accept` header through
  /// its `x-bce-process=image/format,f_auto` transform. Some mobile decoders
  /// fail on those, so drop only the image-processing query to get the
  /// original uploaded JPEG/PNG.
  String _originalImageUrl(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.queryParameters.containsKey('x-bce-process')) {
      return url;
    }
    final params = Map<String, String>.from(uri.queryParameters)
      ..remove('x-bce-process');
    final query = params.entries
        .map((entry) =>
            '${Uri.encodeQueryComponent(entry.key)}=${Uri.encodeQueryComponent(entry.value)}')
        .join('&');
    return uri.replace(query: query).toString();
  }

  List<String> _imageCandidates(String src, String baseUrl) {
    final resolved = _resolveImageUrl(src, baseUrl);
    if (resolved.isEmpty) return const [];
    final original = _originalImageUrl(resolved);
    return original == resolved ? [resolved] : [original, resolved];
  }

  String _prepareArticleHtml(String html, String baseUrl) {
    if (html.trim().isEmpty) return '';
    return html.replaceAllMapped(
      RegExp(r'<img\b[^>]*>', caseSensitive: false),
      (match) {
        final tag = match.group(0) ?? '';
        final src = _htmlAttr(tag, ['data-src', 'data-original', 'src']);
        if (src == null) return '';
        final resolved =
            _resolveImageUrl(src, baseUrl).replaceAll('"', '&quot;');
        final alt = (_htmlAttr(tag, ['alt']) ?? '').replaceAll('"', '&quot;');
        return '<img src="$resolved" alt="$alt" />';
      },
    );
  }

  /// flutter_html's built-in image renderer feeds the CSS width value straight
  /// into `Image.network(width: ...)`, so a `100%` style becomes 100 logical
  /// pixels. Render article images ourselves to keep them full width and to
  /// retry with the original asset when a CDN transform fails.
  ImageExtension _articleImageExtension(String baseUrl) {
    return ImageExtension(
      builder: (context) {
        final src = context.attributes['src'];
        if (src == null || src.isEmpty) return const SizedBox.shrink();
        return ArticleImage(
          candidates: _imageCandidates(src, baseUrl),
          alt: context.attributes['alt'] ?? '',
        );
      },
    );
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
    final content = (entry['content'] ?? '').toString().trim();
    final summary = (entry['summary'] ?? '').toString().trim();
    final rawHtml = _prepareArticleHtml(
      content.isNotEmpty ? content : summary,
      link,
    );

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
                if (rawHtml.isEmpty)
                  SelectableText(
                    '暂无正文，可打开原文查看。',
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.85,
                      color: palette.ink,
                    ),
                  )
                else
                  SelectionArea(
                    child: Html(
                      data: rawHtml,
                      doNotRenderTheseTags: const {'script', 'style', 'iframe'},
                      extensions: [_articleImageExtension(link)],
                      onLinkTap: (url, attributes, element) {
                        if (url != null && url.isNotEmpty) {
                          _openLink(url);
                        }
                      },
                      style: {
                        'body': Style(
                          margin: Margins.zero,
                          padding: HtmlPaddings.zero,
                          fontSize: FontSize(14),
                          lineHeight: LineHeight(1.85),
                          color: palette.ink,
                        ),
                        'p': Style(margin: Margins.only(bottom: 10)),
                        'h1': Style(
                          fontSize: FontSize(21),
                          lineHeight: LineHeight(1.35),
                          margin: Margins.only(bottom: 10),
                        ),
                        'h2': Style(
                          fontSize: FontSize(18),
                          lineHeight: LineHeight(1.4),
                          margin: Margins.only(top: 14, bottom: 8),
                        ),
                        'h3': Style(
                          fontSize: FontSize(16),
                          lineHeight: LineHeight(1.45),
                          margin: Margins.only(top: 12, bottom: 6),
                        ),
                        'a': Style(
                          color: palette.primary,
                          textDecoration: TextDecoration.underline,
                        ),
                        'img': Style(
                          margin: Margins.only(top: 4, bottom: 4),
                        ),
                        'blockquote': Style(
                          margin: Margins.only(top: 8, bottom: 8),
                          padding: HtmlPaddings.only(left: 12),
                          border: Border(
                            left: BorderSide(color: palette.line, width: 3),
                          ),
                        ),
                        'li': Style(margin: Margins.only(bottom: 4)),
                        'code': Style(
                          backgroundColor: palette.background,
                          fontFamily: 'monospace',
                        ),
                        'pre': Style(
                          backgroundColor: palette.background,
                          padding: HtmlPaddings.all(10),
                        ),
                      },
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

  Widget _filterChip(
    AppPalette palette, {
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 140),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? palette.primary : palette.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected ? palette.primary : palette.line,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11.5,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? Colors.white : palette.muted,
          ),
        ),
      ),
    );
  }

  Widget _entryTile(AppPalette palette, Map<String, dynamic> entry) {
    final unread = entry['read'] == false;
    final preview = _preview(entry);
    final published = _formatPublished(entry['published']);
    return AppCard(
      onTap: () => _open(entry),
      padding: EdgeInsets.zero,
      color:
          unread ? palette.primarySoft.withValues(alpha: 0.38) : palette.card,
      borderColor:
          unread ? palette.primary.withValues(alpha: 0.4) : palette.line,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 11, 13, 11),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 3,
              height: 42,
              margin: const EdgeInsets.only(top: 2, right: 10),
              decoration: BoxDecoration(
                color: unread ? palette.primary : Colors.transparent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          (entry['title'] ?? '').toString(),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 13,
                            height: 1.4,
                            fontWeight:
                                unread ? FontWeight.w800 : FontWeight.w500,
                            color: unread
                                ? palette.ink
                                : palette.ink.withValues(alpha: 0.62),
                          ),
                        ),
                      ),
                      if (unread) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: palette.primary,
                            borderRadius: BorderRadius.circular(7),
                          ),
                          child: const Text(
                            '未读',
                            style: TextStyle(
                              fontSize: 8.5,
                              fontWeight: FontWeight.w700,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (preview.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      preview,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10.5,
                        height: 1.5,
                        color: unread
                            ? palette.ink.withValues(alpha: 0.72)
                            : palette.muted.withValues(alpha: 0.8),
                      ),
                    ),
                  ],
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      if (unread) ...[
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
                          (entry['source_title'] ?? '资讯').toString(),
                          style: TextStyle(
                            fontSize: 9.5,
                            fontWeight: FontWeight.w700,
                            color: unread
                                ? palette.primary
                                : palette.muted.withValues(alpha: 0.85),
                          ),
                        ),
                      ),
                      if (published.isNotEmpty)
                        Text(
                          published,
                          style: TextStyle(
                            fontSize: 9,
                            color: palette.muted.withValues(alpha: 0.7),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
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
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Row(
                children: [
                  _filterChip(
                    palette,
                    label: '全部 ${_entries.length}',
                    selected: !_onlyUnread,
                    onTap: () => setState(() => _onlyUnread = false),
                  ),
                  const SizedBox(width: 8),
                  _filterChip(
                    palette,
                    label: '未读 $_unreadCount',
                    selected: _onlyUnread,
                    onTap: () => setState(() => _onlyUnread = true),
                  ),
                ],
              ),
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
                          : _visible.isEmpty
                              ? ListView(
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  children: [
                                    const SizedBox(height: 50),
                                    if (_onlyUnread)
                                      EmptyState(
                                        icon: Icons.mark_email_read_outlined,
                                        title: '没有未读资讯',
                                        subtitle: '全部内容都已读过了。',
                                      )
                                    else
                                      const EmptyState(
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
                                  itemCount: _visible.length,
                                  itemBuilder: (context, index) {
                                    final entry = _visible[index];
                                    return Padding(
                                      padding: const EdgeInsets.only(bottom: 8),
                                      child: _entryTile(palette, entry),
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
