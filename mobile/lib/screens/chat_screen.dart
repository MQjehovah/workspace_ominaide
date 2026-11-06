import 'package:flutter/material.dart';

import '../models/chat_session.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  final String? initialQuery;
  final String? sessionId;
  final String? title;
  final String? contextLabel;

  /// When true and no [sessionId] is given, open the most recent conversation
  /// instead of starting a blank chat. Used by the 对话 tab.
  final bool autoLoadLatest;

  const ChatScreen({
    super.key,
    this.initialQuery,
    this.sessionId,
    this.title,
    this.contextLabel,
    this.autoLoadLatest = false,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _Message {
  final String role;
  String text;
  bool error = false;

  _Message(this.role, this.text);
}

class _ChatScreenState extends State<ChatScreen> {
  final List<_Message> _messages = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _loading = false;
  bool _bootstrapping = false;

  late String _sessionId =
      widget.sessionId ?? 'mobile-${DateTime.now().microsecondsSinceEpoch}';
  String? _title;

  @override
  void initState() {
    super.initState();
    _title = widget.title;
    _bootstrap();
    if (widget.initialQuery != null && widget.initialQuery!.isNotEmpty) {
      _input.text = widget.initialQuery!;
      WidgetsBinding.instance.addPostFrameCallback((_) => _send());
    }
  }

  Future<void> _bootstrap() async {
    if (widget.sessionId != null) {
      await _loadHistory();
      return;
    }
    if (!widget.autoLoadLatest || widget.initialQuery != null) return;
    _bootstrapping = true;
    try {
      final sessions = await ApiService().listChatSessions();
      if (!mounted) return;
      if (sessions.isNotEmpty) {
        _sessionId = sessions.first.id;
        _title = sessions.first.title;
        await _loadHistory();
      }
    } catch (_) {
      // Offline: stay on a blank new conversation.
    } finally {
      if (mounted) setState(() => _bootstrapping = false);
    }
  }

  void _newChat() {
    setState(() {
      _sessionId = 'mobile-${DateTime.now().microsecondsSinceEpoch}';
      _title = null;
      _messages.clear();
      _loading = false;
      _bootstrapping = false;
    });
    _input.clear();
  }

  Future<void> _switchSession(ChatSession session) async {
    setState(() {
      _sessionId = session.id;
      _title = session.title;
      _messages.clear();
      _loading = false;
    });
    await _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final rows = await ApiService().loadChatHistory(
        sessionId: _sessionId,
        limit: 50,
      );
      if (!mounted || rows.isEmpty) return;
      // Never overwrite a turn that started before history arrived.
      if (_messages.isNotEmpty || _loading) return;
      final loaded = <_Message>[];
      for (final row in rows) {
        final role = (row['role'] ?? 'assistant').toString();
        final content = (row['content'] ?? '').toString();
        if (content.isEmpty) continue;
        loaded.add(_Message(role == 'user' ? 'user' : 'assistant', content));
      }
      if (loaded.isEmpty) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(loaded);
      });
      _scrollToBottom();
    } catch (_) {
      // Offline or first run: keep the local empty state.
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _loading) return;
    _input.clear();

    final history = _messages
        .where((m) => m.text.isNotEmpty && !m.error)
        .toList()
        .reversed
        .take(20)
        .toList()
        .reversed
        .map((m) => {'role': m.role, 'content': m.text})
        .toList();

    final assistant = _Message('assistant', '');
    if (_title == null) {
      _title = text.length > 20 ? '${text.substring(0, 20)}…' : text;
    }
    setState(() {
      _messages.add(_Message('user', text));
      _messages.add(assistant);
      _loading = true;
    });
    _scrollToBottom();

    try {
      final api = ApiService();
      await for (final chunk in api.chatStream(
        text,
        history: history,
        sessionId: _sessionId,
      )) {
        if (!mounted) return;
        setState(() => assistant.text += chunk);
        _scrollToBottom();
      }
      if (mounted && assistant.text.isEmpty) {
        setState(() => assistant.text = '（无回复）');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        assistant.text = e.toString().replaceFirst('Exception: ', '');
        assistant.error = true;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _retry() async {
    if (_loading || _messages.isEmpty) return;
    String? lastUser;
    for (final message in _messages.reversed) {
      if (message.role == 'user') {
        lastUser = message.text;
        break;
      }
    }
    if (lastUser == null) return;
    setState(() {
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        _messages.removeLast();
      }
      if (_messages.isNotEmpty && _messages.last.role == 'user') {
        _messages.removeLast();
      }
    });
    _input.text = lastUser;
    await _send();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  void _applyPrompt(String text) {
    _input.text = text;
    _input.selection = TextSelection.fromPosition(
      TextPosition(offset: _input.text.length),
    );
    _send();
  }

  Future<void> _showReferences() async {
    final api = ApiService();
    final now = DateTime.now();
    final start = DateTime(now.year, now.month, now.day);
    List<Map<String, dynamic>> events = [];
    List<Map<String, dynamic>> todos = [];
    try {
      events = await api.listScheduleEvents(
        start: start.toIso8601String(),
        end: start.add(const Duration(days: 1)).toIso8601String(),
      );
    } catch (_) {}
    try {
      todos = await api.listTodoItems();
    } catch (_) {}
    if (!mounted) return;

    final picked = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (context) {
        final palette = AppPalette.of(context);
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              Text(
                '引用到今天的内容',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 8),
              if (events.isEmpty && todos.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  child: Text(
                    '今天没有日程或待办可以引用。',
                    style: TextStyle(fontSize: 13, color: palette.muted),
                  ),
                ),
              for (final event in events.take(6))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.event_outlined, color: palette.primary),
                  title: Text(
                    (event['title'] ?? '日程').toString(),
                    style: TextStyle(fontSize: 13, color: palette.ink),
                  ),
                  subtitle: Text(
                    (event['start_time'] ?? '').toString().replaceFirst('T', ' '),
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                  onTap: () => Navigator.pop(
                    context,
                    '关于今天的日程「${event['title']}」，',
                  ),
                ),
              for (final todo in todos.take(6))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.check_circle_outline, color: palette.success),
                  title: Text(
                    (todo['title'] ?? '待办').toString(),
                    style: TextStyle(fontSize: 13, color: palette.ink),
                  ),
                  subtitle: Text(
                    '待办',
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                  onTap: () => Navigator.pop(
                    context,
                    '关于待办「${todo['title']}」，',
                  ),
                ),
            ],
          ),
        );
      },
    );
    if (picked == null || !mounted) return;
    _input.text = picked + _input.text;
    _input.selection = TextSelection.fromPosition(
      TextPosition(offset: _input.text.length),
    );
  }

  Future<void> _showHistory() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (sheetContext) {
        final palette = AppPalette.of(sheetContext);
        return SafeArea(
          child: FutureBuilder<List<ChatSession>>(
            future: ApiService().listChatSessions(),
            builder: (context, snapshot) {
              final items = snapshot.data ?? [];
              return ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                children: [
                  Text(
                    '会话',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: palette.ink,
                    ),
                  ),
                  const SizedBox(height: 8),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.add_circle_outline, color: palette.primary),
                    title: Text(
                      '新对话',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: palette.primary,
                      ),
                    ),
                    onTap: () {
                      Navigator.pop(sheetContext);
                      _newChat();
                    },
                  ),
                  if (snapshot.connectionState == ConnectionState.waiting)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (items.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 20),
                      child: Text(
                        '还没有历史会话。',
                        style: TextStyle(fontSize: 13, color: palette.muted),
                      ),
                    ),
                  for (final session in items.take(30))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        session.id == _sessionId
                            ? Icons.chat_bubble_rounded
                            : Icons.chat_bubble_outline,
                        color: session.id == _sessionId
                            ? palette.primary
                            : palette.muted,
                      ),
                      title: Text(
                        session.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: session.id == _sessionId
                              ? FontWeight.w800
                              : FontWeight.w500,
                          color: palette.ink,
                        ),
                      ),
                      subtitle: Text(
                        relativeTimeLabel(session.updatedAt),
                        style: TextStyle(fontSize: 11, color: palette.muted),
                      ),
                      onTap: () {
                        Navigator.pop(sheetContext);
                        _switchSession(session);
                      },
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
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
            _buildTopBar(palette),
            if (widget.contextLabel != null) _buildContextBanner(palette),
            Expanded(
              child: _bootstrapping
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary),
                    )
                  : _messages.isEmpty
                      ? _buildEmpty(palette)
                      : ListView.builder(
                          controller: _scroll,
                          padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
                          itemCount: _messages.length,
                          itemBuilder: (context, index) {
                            final message = _messages[index];
                            final isLast = index == _messages.length - 1;
                            return ChatBubble(
                              role: message.role,
                              text: message.text,
                              streaming: isLast && _loading,
                              error: message.error,
                              onRetry: message.error ? _retry : null,
                            );
                          },
                        ),
            ),
            _buildComposer(palette),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 4, 10, 8),
      decoration: BoxDecoration(
        color: palette.card.withValues(alpha: 0.78),
        border: Border(bottom: BorderSide(color: palette.line)),
      ),
      child: Row(
        children: [
          if (Navigator.of(context).canPop()) ...[
            RoundIconButton(
              icon: Icons.chevron_left_rounded,
              onTap: () => Navigator.maybePop(context),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: InkWell(
              onTap: _showHistory,
              borderRadius: BorderRadius.circular(10),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _title ?? '新对话',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                          ),
                          Text(
                            '点击切换会话',
                            style: TextStyle(fontSize: 10.5, color: palette.muted),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      Icons.expand_more_rounded,
                      size: 17,
                      color: palette.muted,
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          RoundIconButton(
            icon: Icons.add_rounded,
            tooltip: '新对话',
            onTap: _newChat,
          ),
        ],
      ),
    );
  }

  Widget _buildContextBanner(AppPalette palette) {
    return Container(
      margin: const EdgeInsets.fromLTRB(14, 8, 14, 0),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: palette.primarySoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: palette.line),
      ),
      child: Row(
        children: [
          TagDot(color: palette.primary),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              widget.contextLabel!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
                color: palette.primary,
              ),
            ),
          ),
          Icon(Icons.close_rounded, size: 14, color: palette.muted),
        ],
      ),
    );
  }

  Widget _buildEmpty(AppPalette palette) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 30, 22, 20),
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [palette.primaryLight, palette.primary],
            ),
            borderRadius: BorderRadius.circular(19),
          ),
          child: const Icon(Icons.auto_awesome, color: Colors.white, size: 26),
        ),
        const SizedBox(height: 16),
        Text(
          '今天想先处理什么？',
          style: TextStyle(
            fontSize: 21,
            height: 1.15,
            letterSpacing: -0.4,
            fontWeight: FontWeight.w800,
            color: palette.ink,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '可以直接问，也可以让我查日程、待办、文件，或帮你起草回复。',
          style: TextStyle(fontSize: 12.5, height: 1.65, color: palette.muted),
        ),
        const SizedBox(height: 18),
        for (final prompt in const [
          '帮我看看今天最重要的三件事',
          '整理一下我的收件箱',
          '写本周周报',
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: AppCard(
              onTap: () => _applyPrompt(prompt),
              child: Row(
                children: [
                  Icon(Icons.north_east_rounded, size: 16, color: palette.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      prompt,
                      style: TextStyle(fontSize: 12.5, color: palette.ink),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildComposer(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 7, 12, 6),
      decoration: BoxDecoration(
        color: palette.card.withValues(alpha: 0.82),
        border: Border(top: BorderSide(color: palette.line)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              InkWell(
                onTap: _showReferences,
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: palette.primarySoft,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(Icons.add_rounded, size: 20, color: palette.primary),
                ),
              ),
              const SizedBox(width: 7),
              Expanded(
                child: TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  style: TextStyle(fontSize: 14, color: palette.ink),
                  decoration: InputDecoration(
                    hintText: '继续问，或让我处理一件事…',
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 13,
                      vertical: 10,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 7),
              InkWell(
                onTap: _loading ? null : _send,
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [palette.primaryLight, palette.primary],
                    ),
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: palette.primary.withValues(alpha: 0.22),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Icon(
                    _loading ? Icons.more_horiz_rounded : Icons.send_rounded,
                    color: Colors.white,
                    size: 18,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
