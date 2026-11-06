import 'package:flutter/material.dart';

import '../models/chat_session.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'chat_screen.dart';

class ChatListScreen extends StatefulWidget {
  const ChatListScreen({super.key});

  @override
  State<ChatListScreen> createState() => _ChatListScreenState();
}

class _ChatListScreenState extends State<ChatListScreen> {
  final _searchController = TextEditingController();
  List<ChatSession> _sessions = [];
  bool _loading = true;
  bool _searching = false;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final sessions = await ApiService().listChatSessions();
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  List<ChatSession> get _filtered {
    if (_query.trim().isEmpty) return _sessions;
    final q = _query.toLowerCase();
    return _sessions
        .where((session) => session.title.toLowerCase().contains(q))
        .toList();
  }

  Future<void> _open(ChatSession? session) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ChatScreen(
          sessionId: session?.id,
          title: session?.title,
        ),
      ),
    );
    if (mounted) _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
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
              kicker: 'Chat',
              title: '对话',
              subtitle: _sessions.isEmpty
                  ? '和你的 AI 幕僚聊点什么'
                  : '${_sessions.length} 个进行中的会话',
              actions: [
                RoundIconButton(
                  icon: _searching ? Icons.close_rounded : Icons.search_rounded,
                  tooltip: '搜索会话',
                  onTap: () {
                    setState(() {
                      _searching = !_searching;
                      if (!_searching) {
                        _searchController.clear();
                        _query = '';
                      }
                    });
                  },
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建对话',
                  onTap: () => _open(null),
                ),
              ],
            ),
            if (_searching)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                child: AppSearchBar(
                  controller: _searchController,
                  hint: '搜索会话',
                  autofocus: true,
                  onChanged: (value) => setState(() => _query = value),
                ),
              ),
            Expanded(
              child: _loading
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _filtered.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                EmptyState(
                                  icon: Icons.chat_bubble_outline_rounded,
                                  title: _query.isEmpty ? '还没有对话' : '没有找到相关会话',
                                  subtitle: _query.isEmpty
                                      ? '从一句话开始。可以让 AI 查日程、整理收件箱，或起草回复。'
                                      : '换个关键词试试。',
                                  action: _query.isEmpty
                                      ? _NewChatButton(onTap: () => _open(null))
                                      : null,
                                ),
                              ],
                            )
                          : ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              children: [
                                _NewChatButton(onTap: () => _open(null)),
                                const SizedBox(height: 12),
                                for (final session in _filtered)
                                  _SessionRow(
                                    session: session,
                                    onTap: () => _open(session),
                                  ),
                              ],
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NewChatButton extends StatelessWidget {
  const _NewChatButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [palette.primaryLight, palette.primary],
            ),
            borderRadius: BorderRadius.circular(14),
            boxShadow: [
              BoxShadow(
                color: palette.primary.withValues(alpha: 0.22),
                blurRadius: 14,
                offset: const Offset(0, 5),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.auto_awesome, color: Colors.white, size: 17),
                const SizedBox(width: 7),
                Text(
                  '开始新对话',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SessionRow extends StatelessWidget {
  const _SessionRow({required this.session, required this.onTap});

  final ChatSession session;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: palette.primarySoft,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                Icons.auto_awesome,
                size: 17,
                color: palette.primary,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    session.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      color: palette.ink,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '继续这段对话',
                    style: TextStyle(fontSize: 10.5, color: palette.muted),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              relativeTimeLabel(session.updatedAt),
              style: TextStyle(fontSize: 10, color: palette.muted),
            ),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right_rounded, size: 18, color: palette.muted),
          ],
        ),
      ),
    );
  }
}
