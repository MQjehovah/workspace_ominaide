import 'package:flutter/material.dart';
import '../services/api_service.dart';

class ChatScreen extends StatefulWidget {
  final String? initialQuery;
  const ChatScreen({super.key, this.initialQuery});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _Message {
  final String role; // user / assistant
  String text;
  _Message(this.role, this.text);
}

class _ChatScreenState extends State<ChatScreen> {
  final List<_Message> _messages = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _loading = false;
  bool _agentMode = false;

  @override
  void initState() {
    super.initState();
    if (widget.initialQuery != null && widget.initialQuery!.isNotEmpty) {
      _input.text = widget.initialQuery!;
      WidgetsBinding.instance.addPostFrameCallback((_) => _send());
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _loading) return;
    _input.clear();
    setState(() {
      _messages.add(_Message('user', text));
      _messages.add(_Message('assistant', ''));
    });
    _loading = true;
    _scrollToBottom();

    // history (last 20, excluding current empty assistant msg)
    final history = _messages
        .where((m) => m.text.isNotEmpty && m.role != 'assistant')
        .toList()
        .reversed
        .take(20)
        .toList()
        .reversed
        .map((m) => {'role': m.role, 'content': m.text})
        .toList();

    try {
      final api = ApiService();
      if (_agentMode) {
        // agent chat (non-streaming for reliability across platforms)
        final reply = await api.chat(text, history: history, agent: true);
        if (!mounted) return;
        setState(() {
          _messages.last.text = reply;
        });
        _scrollToBottom();
      } else {
        // plain chat (non-streaming /api/chat) — returns full reply at once
        final reply = await api.chat(text, history: history);
        if (!mounted) return;
        setState(() {
          _messages.last.text = reply;
        });
        _scrollToBottom();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.last.text = '⚠️ ${e.toString()}';
      });
    } finally {
      _loading = false;
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI 助手')),
      body: Column(
        children: [
          _buildModeBar(),
          Expanded(
            child: _messages.isEmpty
                ? const _EmptyChat()
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.all(12),
                    itemCount: _messages.length,
                    itemBuilder: (c, i) => _MessageBubble(msg: _messages[i], typing: i == _messages.length - 1 && _loading),
                  ),
          ),
          _buildInputBar(),
        ],
      ),
    );
  }

  Widget _buildModeBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceVariant),
      child: Row(
        children: [
          const Text('模式:', style: TextStyle(fontSize: 13)),
          const SizedBox(width: 8),
          Expanded(
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: false, label: Text('对话')),
                ButtonSegment(value: true, label: Text('Agent')),
              ],
              selected: {_agentMode},
              onSelectionChanged: (s) => setState(() => _agentMode = s.first),
              showSelectedIcon: false,
            ),
          ),
          const SizedBox(width: 8),
          Tooltip(
            message: 'Agent 模式会调用工具(日程/待办/搜索等),对话模式仅生成文本',
            child: const Icon(Icons.info_outline, size: 18, color: Colors.grey),
          ),
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: _input,
                minLines: 1,
                maxLines: 4,
                decoration: InputDecoration(
                  hintText: '输入消息…',
                  isDense: true,
                  filled: true,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(22), borderSide: BorderSide.none),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _loading ? null : _send,
              icon: Icon(_loading ? Icons.more_horiz : Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyChat extends StatelessWidget {
  const _EmptyChat();
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.smart_toy_outlined, size: 64, color: Colors.grey),
          const SizedBox(height: 16),
          Text('问任何问题', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          const Text('对话模式生成文本;Agent 模式可查询日程、待办、文件等', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey)),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final _Message msg;
  final bool typing;
  const _MessageBubble({required this.msg, this.typing = false});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    final scheme = Theme.of(context).colorScheme;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? scheme.primary : scheme.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
          border: isUser ? null : Border.all(color: scheme.outlineVariant),
        ),
        child: msg.text.isEmpty && typing
            ? const _TypingIndicator()
            : SelectableText(msg.text, style: TextStyle(fontSize: 15, color: isUser ? scheme.onPrimary : scheme.onSurface)),
      ),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();
  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator> {
  int _dot = 0;
  @override
  void initState() {
    super.initState();
    Future.doWhile(() async {
      await Future.delayed(const Duration(milliseconds: 400));
      if (!mounted) return false;
      setState(() => _dot = (_dot + 1) % 4);
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 28,
      child: Row(
        children: [
          for (var i = 0; i < 3; i++)
            Padding(
              padding: const EdgeInsets.only(right: 3),
              child: Opacity(opacity: i < _dot ? 1 : 0.2, child: const Text('●', style: TextStyle(fontSize: 8))),
            ),
        ],
      ),
    );
  }
}
