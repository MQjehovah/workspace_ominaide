import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

enum ChatMode { normal, agent }

extension ChatModeX on ChatMode {
  String get label {
    switch (this) {
      case ChatMode.normal:
        return '普通';
      case ChatMode.agent:
        return 'Agent';
    }
  }

  String get hint {
    switch (this) {
      case ChatMode.normal:
        return '直接生成回答';
      case ChatMode.agent:
        return '可以调用日程、待办、文件等工具';
    }
  }
}

class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.role,
    required this.text,
    this.streaming = false,
    this.error = false,
    this.onRetry,
  });

  final String role;
  final String text;
  final bool streaming;
  final bool error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isUser = role == 'user';
    final showTyping = !isUser && streaming && text.isEmpty;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.82,
        ),
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? palette.primary : palette.card,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(15),
            topRight: const Radius.circular(15),
            bottomLeft: Radius.circular(isUser ? 15 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 15),
          ),
          border: isUser ? null : Border.all(color: palette.line),
          boxShadow: isUser
              ? [
                  BoxShadow(
                    color: palette.primary.withValues(alpha: 0.18),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: showTyping
            ? const _TypingRow(key: Key('chat-typing'))
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (error)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline, size: 14, color: palette.accent),
                        const SizedBox(width: 4),
                        Text(
                          '回复失败',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: palette.accent,
                          ),
                        ),
                      ],
                    ),
                  if (error) const SizedBox(height: 4),
                  SelectableText(
                    text,
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.65,
                      color: isUser ? Colors.white : palette.ink,
                    ),
                  ),
                  if (streaming && text.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: _BlinkingCursor(color: palette.primary),
                    ),
                  if (error && onRetry != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: InkWell(
                        onTap: onRetry,
                        child: Text(
                          '重试',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: palette.primary,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}

class _TypingRow extends StatefulWidget {
  const _TypingRow({super.key});

  @override
  State<_TypingRow> createState() => _TypingRowState();
}

class _TypingRowState extends State<_TypingRow> {
  int _dot = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 380), (_) {
      if (!mounted) return;
      setState(() => _dot = (_dot + 1) % 4);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < 3; i++)
          Padding(
            padding: const EdgeInsets.only(right: 3),
            child: Opacity(
              opacity: i < _dot ? 1 : 0.22,
              child: Container(
                width: 5,
                height: 5,
                decoration: BoxDecoration(
                  color: palette.primary,
                  shape: BoxShape.circle,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _BlinkingCursor extends StatefulWidget {
  const _BlinkingCursor({required this.color});

  final Color color;

  @override
  State<_BlinkingCursor> createState() => _BlinkingCursorState();
}

class _BlinkingCursorState extends State<_BlinkingCursor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _controller,
      child: Container(
        width: 2,
        height: 12,
        color: widget.color,
      ),
    );
  }
}
