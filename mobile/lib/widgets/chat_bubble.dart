import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../theme/app_theme.dart';

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

    final bubble = Container(
      constraints: BoxConstraints(
        maxWidth: MediaQuery.of(context).size.width * 0.80,
      ),
      margin: EdgeInsets.only(
        top: 4,
        bottom: 4,
        left: isUser ? 44 : 0,
        right: isUser ? 0 : 10,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        gradient: isUser
            ? LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [palette.primaryLight, palette.primary],
              )
            : null,
        color: isUser ? null : palette.card,
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(18),
          topRight: const Radius.circular(18),
          bottomLeft: Radius.circular(isUser ? 18 : 6),
          bottomRight: Radius.circular(isUser ? 6 : 18),
        ),
        border: isUser
            ? null
            : Border.all(color: palette.line.withValues(alpha: 0.9)),
        boxShadow: [
          BoxShadow(
            color: isUser
                ? palette.primary.withValues(alpha: 0.20)
                : palette.ink.withValues(alpha: 0.04),
            blurRadius: isUser ? 14 : 10,
            offset: const Offset(0, 4),
          ),
        ],
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
                      Icon(Icons.error_outline,
                          size: 14, color: palette.accent),
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
                if (isUser)
                  SelectableText(
                    text,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.65,
                      color: Colors.white,
                    ),
                  )
                else
                  MarkdownBody(
                    data: text,
                    selectable: true,
                    styleSheet: MarkdownStyleSheet(
                      p: TextStyle(
                        fontSize: 14,
                        height: 1.7,
                        color: palette.ink,
                      ),
                      h1: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: palette.ink,
                      ),
                      h2: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        color: palette.ink,
                      ),
                      h3: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: palette.ink,
                      ),
                      code: TextStyle(
                        fontSize: 12,
                        color: palette.primary,
                        backgroundColor: palette.primarySoft,
                      ),
                      codeblockDecoration: BoxDecoration(
                        color: palette.primarySoft,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      blockquoteDecoration: BoxDecoration(
                        color: palette.primarySoft,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      listBullet: TextStyle(
                        fontSize: 14,
                        color: palette.primary,
                      ),
                      a: TextStyle(
                        color: palette.primary,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                if (streaming && text.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: _BlinkingCursor(color: palette.primary),
                  ),
                if (error && onRetry != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: InkWell(
                      onTap: onRetry,
                      borderRadius: BorderRadius.circular(6),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Text(
                          '点击重试',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: palette.primary,
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );

    if (isUser) {
      return Align(alignment: Alignment.centerRight, child: bubble);
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _AssistantAvatar(palette: palette),
        const SizedBox(width: 8),
        Flexible(child: bubble),
      ],
    );
  }
}

class _AssistantAvatar extends StatelessWidget {
  const _AssistantAvatar({required this.palette});

  final AppPalette palette;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 30,
      height: 30,
      margin: const EdgeInsets.only(top: 6),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [palette.primaryLight, palette.primary],
        ),
        borderRadius: BorderRadius.circular(10),
        boxShadow: [
          BoxShadow(
            color: palette.primary.withValues(alpha: 0.18),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: const Icon(Icons.auto_awesome, size: 15, color: Colors.white),
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
