import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class MailScreen extends StatefulWidget {
  const MailScreen({super.key, this.detailId});

  final int? detailId;

  @override
  State<MailScreen> createState() => _MailScreenState();
}

class _MailScreenState extends State<MailScreen> {
  List<Map<String, dynamic>> _messages = [];
  Map<String, dynamic>? _detail;
  bool _loading = true;
  bool _drafting = false;
  bool _error = false;
  String _filter = 'all';

  List<Map<String, dynamic>> get _visibleMessages {
    if (_filter == 'all') return _messages;
    return _messages.where((message) => message['read'] == false).toList();
  }

  int get _unreadCount =>
      _messages.where((message) => message['read'] == false).length;

  @override
  void initState() {
    super.initState();
    if (widget.detailId != null) {
      _loadDetail(widget.detailId!);
    } else {
      _loadList();
    }
  }

  Future<void> _loadList() async {
    setState(() {
      _loading = true;
      _error = false;
    });
    List<Map<String, dynamic>> messages = [];
    try {
      messages = await ApiService().listMailMessages();
    } catch (_) {
      if (mounted) setState(() => _error = true);
    }
    if (!mounted) return;
    setState(() {
      _messages = messages;
      _loading = false;
    });
  }

  Future<void> _loadDetail(int id) async {
    setState(() {
      _loading = true;
      _error = false;
    });
    Map<String, dynamic>? detail;
    try {
      detail = await ApiService().getMailMessage(id);
      if (detail != null) {
        await ApiService().put('/plugins/mail/messages/$id/read', const {});
      }
    } catch (_) {
      if (mounted) setState(() => _error = true);
    }
    if (!mounted) return;
    setState(() {
      _detail = detail;
      _loading = false;
    });
  }

  Future<void> _draft() async {
    final detail = _detail;
    if (detail == null || _drafting) return;
    setState(() => _drafting = true);
    Map<String, dynamic>? draft;
    try {
      draft = await ApiService().getDraftReply(
        source: 'mail',
        messageId: detail['id'] is int ? detail['id'] as int : null,
        botId: BotSelectionService().botId,
      );
    } catch (_) {}
    if (!mounted) return;
    setState(() => _drafting = false);
    if (draft == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('生成草稿失败')),
      );
      return;
    }
    final subject = (draft['subject'] ?? '').toString();
    final body = (draft['body'] ?? '').toString();
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) {
        final palette = AppPalette.of(context);
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '回复草稿',
            style: TextStyle(fontSize: 16, color: palette.ink),
          ),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  subject,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  body,
                  style: TextStyle(
                    fontSize: 12.5,
                    height: 1.7,
                    color: palette.muted,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  (draft!['note'] ?? '').toString(),
                  style: TextStyle(fontSize: 10, color: palette.muted),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
            FilledButton(
              onPressed: () async {
                await Clipboard.setData(
                  ClipboardData(text: '主题：$subject\n\n$body'),
                );
                if (!context.mounted) return;
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('草稿已复制')),
                );
              },
              child: const Text('复制草稿'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: widget.detailId == null ? _buildList(palette) : _buildDetail(palette),
      ),
    );
  }

  Widget _filterChip(String key, String label, AppPalette palette) {
    final selected = _filter == key;
    return InkWell(
      onTap: () => setState(() => _filter = key),
      borderRadius: BorderRadius.circular(18),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? palette.primary : palette.card,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: selected ? palette.primary : palette.line,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: selected ? Colors.white : palette.muted,
          ),
        ),
      ),
    );
  }

  Widget _buildList(AppPalette palette) {
    return Column(
      children: [
        PageHeader(
          kicker: 'Mail',
          title: '邮件',
          subtitle: _loading
              ? '加载中'
              : '$_unreadCount 封未读 · 共 ${_messages.length} 封',
          actions: [
            RoundIconButton(
              icon: Icons.arrow_back_rounded,
              onTap: () => Navigator.maybePop(context),
            ),
            const SizedBox(width: 6),
            RoundIconButton(
              icon: Icons.refresh_rounded,
              tooltip: '刷新',
              onTap: _loadList,
            ),
          ],
        ),
        SizedBox(
          height: 36,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              _filterChip('all', '全部 ${_messages.length}', palette),
              const SizedBox(width: 6),
              _filterChip('unread', '未读 $_unreadCount', palette),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Expanded(
          child: _loading
              ? Center(child: CircularProgressIndicator(color: palette.primary))
              : RefreshIndicator(
                  onRefresh: _loadList,
                  color: palette.primary,
                  child: _error
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _loadList),
                          ],
                        )
                      : _visibleMessages.isEmpty
                          ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 50),
                            EmptyState(
                              icon: Icons.mail_outline_rounded,
                              title: _filter == 'unread' ? '没有未读邮件' : '还没有邮件',
                              subtitle: _filter == 'unread'
                                  ? '所有邮件都已读完。'
                                  : '在 Web 或桌面端配置邮箱后，邮件会同步到这里。',
                            ),
                          ],
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                          itemCount: _visibleMessages.length,
                          itemBuilder: (context, index) {
                            final message = _visibleMessages[index];
                            return _MailRow(
                              message: message,
                              onTap: () async {
                                final id = message['id'];
                                if (id is! int) return;
                                await Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => MailScreen(detailId: id),
                                  ),
                                );
                                if (mounted) _loadList();
                              },
                            );
                          },
                        ),
                ),
        ),
      ],
    );
  }

  Widget _buildDetail(AppPalette palette) {
    if (_loading) {
      return Center(child: CircularProgressIndicator(color: palette.primary));
    }
    if (_error) {
      return Column(
        children: [
          PageHeader(
            kicker: 'Mail',
            title: '邮件详情',
            actions: [
              RoundIconButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.maybePop(context),
              ),
            ],
          ),
          Expanded(
            child: ErrorState(
              onRetry: () {
                final id = widget.detailId;
                if (id != null) _loadDetail(id);
              },
            ),
          ),
        ],
      );
    }
    final detail = _detail;
    if (detail == null) {
      return Column(
        children: [
          PageHeader(
            kicker: 'Mail',
            title: '邮件详情',
            actions: [
              RoundIconButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.maybePop(context),
              ),
            ],
          ),
          const Expanded(
            child: EmptyState(
              icon: Icons.mail_outline_rounded,
              title: '找不到这封邮件',
              subtitle: '它可能已经被删除。',
            ),
          ),
        ],
      );
    }
    return Column(
      children: [
        PageHeader(
          kicker: 'Mail',
          title: '邮件详情',
          actions: [
            RoundIconButton(
              icon: Icons.arrow_back_rounded,
              onTap: () => Navigator.maybePop(context),
            ),
          ],
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
            children: [
              Text(
                (detail['subject'] ?? '(无主题)').toString(),
                style: TextStyle(
                  fontSize: 19,
                  height: 1.3,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                [
                  (detail['from_address'] ?? '').toString(),
                  (detail['date'] ?? '').toString().replaceFirst('T', ' '),
                ].where((e) => e.isNotEmpty).join(' · '),
                style: TextStyle(fontSize: 11, color: palette.muted),
              ),
              const SizedBox(height: 14),
              AppCard(
                child: Text(
                  (detail['content'] ?? detail['preview'] ?? '').toString(),
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.8,
                    color: palette.ink,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: _drafting ? null : _draft,
                icon: _drafting
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.auto_awesome, size: 17),
                label: Text(_drafting ? '生成中…' : '起草回复'),
                style: FilledButton.styleFrom(
                  backgroundColor: palette.primary,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _MailRow extends StatelessWidget {
  const _MailRow({required this.message, required this.onTap});

  final Map<String, dynamic> message;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final unread = message['read'] == false;
    final important = message['important'] == true;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
        color: unread ? palette.primarySoft : null,
        borderColor: unread
            ? palette.primary.withValues(alpha: 0.28)
            : palette.line,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: unread
                        ? palette.primary.withValues(alpha: 0.16)
                        : palette.line.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    unread
                        ? (important
                            ? Icons.mark_email_unread_rounded
                            : Icons.mail_rounded)
                        : Icons.drafts_outlined,
                    size: 16,
                    color: unread ? palette.primary : palette.muted,
                  ),
                ),
                if (unread)
                  Positioned(
                    top: -2,
                    right: -2,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: palette.accent,
                        shape: BoxShape.circle,
                        border: Border.all(color: palette.card, width: 1.5),
                      ),
                    ),
                  ),
              ],
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
                          (message['subject'] ?? '(无主题)').toString(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12.5,
                            fontWeight:
                                unread ? FontWeight.w800 : FontWeight.w500,
                            color: unread ? palette.ink : palette.muted,
                          ),
                        ),
                      ),
                      if (important)
                        Icon(Icons.priority_high_rounded,
                            size: 13, color: palette.accent),
                      const SizedBox(width: 5),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: unread
                              ? palette.primary.withValues(alpha: 0.12)
                              : palette.line.withValues(alpha: 0.55),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          unread ? '未读' : '已读',
                          style: TextStyle(
                            fontSize: 9,
                            fontWeight: FontWeight.w800,
                            color: unread ? palette.primary : palette.muted,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    (message['from_address'] ?? '').toString(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 10.5,
                      color: unread ? palette.ink : palette.muted,
                      fontWeight: unread ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    (message['ai_summary'] ?? message['preview'] ?? '').toString(),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 10.5,
                      height: 1.5,
                      color: palette.muted,
                    ),
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
