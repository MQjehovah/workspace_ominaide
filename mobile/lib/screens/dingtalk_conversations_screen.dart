import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/loading_state.dart';

/// Read-only DingTalk conversation viewer backed by the plugin cache.
class DingTalkConversationsScreen extends StatefulWidget {
  const DingTalkConversationsScreen({super.key});

  @override
  State<DingTalkConversationsScreen> createState() =>
      _DingTalkConversationsScreenState();
}

class _DingTalkConversationsScreenState
    extends State<DingTalkConversationsScreen> {
  List<Map<String, dynamic>> _conversations = [];
  bool _loading = true;
  bool _error = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = _conversations.isEmpty;
      _error = false;
    });
    try {
      final items = await ApiService().dingtalkConversations();
      if (!mounted) return;
      setState(() {
        _conversations = items;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = true;
      });
    }
  }

  Future<void> _open(Map<String, dynamic> conversation) async {
    final name = (conversation['name'] ?? conversation['conversation_id'])
        .toString();
    final id = (conversation['conversation_id'] ?? '').toString();
    if (id.isEmpty) return;
    setState(() => conversation['unread_count'] = 0);
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _ConversationPage(conversationId: id, title: name),
      ),
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
              kicker: 'DingTalk',
              title: '钉钉会话',
              subtitle: '只读查看已同步的会话与消息',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
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
                  ? const SkeletonList(count: 4)
                  : _error
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _load),
                          ],
                        )
                      : RefreshIndicator(
                          onRefresh: _load,
                          color: palette.primary,
                          child: _conversations.isEmpty
                              ? ListView(
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  children: const [
                                    SizedBox(height: 50),
                                    EmptyState(
                                      icon: Icons.forum_outlined,
                                      title: '还没有同步会话',
                                      subtitle: '绑定钉钉后，插件会定时同步会话和消息。',
                                    ),
                                  ],
                                )
                              : ListView.builder(
                                  padding:
                                      const EdgeInsets.fromLTRB(16, 8, 16, 24),
                                  itemCount: _conversations.length,
                                  itemBuilder: (context, index) {
                                    final item = _conversations[index];
                                    return Padding(
                                      padding: const EdgeInsets.only(bottom: 9),
                                      child: _conversationCard(palette, item),
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

  Widget _conversationCard(AppPalette palette, Map<String, dynamic> item) {
    final unread = (item['unread_count'] as num?)?.toInt() ?? 0;
    final last = (item['last_message_at'] ?? '').toString();
    return AppCard(
      child: InkWell(
        onTap: () => _open(item),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: palette.primary.withValues(alpha: 0.12),
                child: Icon(
                  Icons.chat_bubble_outline_rounded,
                  size: 18,
                  color: palette.primary,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      (item['name'] ?? item['conversation_id']).toString(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: palette.ink,
                      ),
                    ),
                    if (last.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        last.replaceFirst('T', ' ').split('.').first,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 10, color: palette.muted),
                      ),
                    ],
                  ],
                ),
              ),
              if (unread > 0)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: palette.primary,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '$unread',
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                    ),
                  ),
                ),
              const SizedBox(width: 4),
              Icon(Icons.chevron_right_rounded, color: palette.muted),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConversationPage extends StatefulWidget {
  const _ConversationPage({required this.conversationId, required this.title});

  final String conversationId;
  final String title;

  @override
  State<_ConversationPage> createState() => _ConversationPageState();
}

class _ConversationPageState extends State<_ConversationPage> {
  List<Map<String, dynamic>> _messages = [];
  bool _loading = true;
  bool _error = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = _messages.isEmpty;
      _error = false;
    });
    try {
      final items = await ApiService().dingtalkMessages(widget.conversationId);
      final lastId = items.isEmpty
          ? null
          : (items.last['message_id'] ?? '').toString();
      unawaited(ApiService().markDingtalkRead(
        widget.conversationId,
        messageId: lastId,
      ));
      if (!mounted) return;
      setState(() {
        _messages = items;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = true;
      });
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
              kicker: 'DingTalk',
              title: widget.title,
              subtitle: '${_messages.length} 条消息',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
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
                  ? const SkeletonList(count: 5)
                  : _error
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _load),
                          ],
                        )
                      : _messages.isEmpty
                          ? const EmptyState(
                              icon: Icons.chat_bubble_outline_rounded,
                              title: '暂无消息',
                              subtitle: '下一次同步后，这里会显示会话内容。',
                            )
                          : ListView.builder(
                              padding:
                                  const EdgeInsets.fromLTRB(16, 8, 16, 24),
                              itemCount: _messages.length,
                              itemBuilder: (context, index) {
                                final msg = _messages[index];
                                final sender =
                                    (msg['sender'] ?? '').toString().trim();
                                final text = (msg['text'] ?? '').toString();
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: AppCard(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        if (sender.isNotEmpty) ...[
                                          Text(
                                            sender,
                                            style: TextStyle(
                                              fontSize: 11,
                                              fontWeight: FontWeight.w700,
                                              color: palette.primary,
                                            ),
                                          ),
                                          const SizedBox(height: 4),
                                        ],
                                        Text(
                                          text,
                                          style: TextStyle(
                                            fontSize: 13,
                                            height: 1.5,
                                            color: palette.ink,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
            ),
          ],
        ),
      ),
    );
  }
}
