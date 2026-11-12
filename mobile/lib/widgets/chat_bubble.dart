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
    this.onContinue,
  });

  final String role;
  final String text;
  final bool streaming;
  final bool error;
  final VoidCallback? onRetry;
  final VoidCallback? onContinue;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isUser = role == 'user';
    final showTyping = !isUser && streaming && text.isEmpty;

    final bubble = Container(
      constraints: BoxConstraints(
        maxWidth: MediaQuery.of(context).size.width * 0.72,
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
                ? palette.primary.withValues(alpha: 0.18)
                : palette.ink.withValues(alpha: 0.04),
            blurRadius: isUser ? 12 : 8,
            offset: const Offset(0, 3),
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
                if (error && (onContinue != null || onRetry != null))
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Wrap(
                      spacing: 14,
                      children: [
                        if (onContinue != null)
                          InkWell(
                            onTap: onContinue,
                            borderRadius: BorderRadius.circular(6),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Text(
                                '继续生成',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                  color: palette.primary,
                                ),
                              ),
                            ),
                          ),
                        if (onRetry != null)
                          InkWell(
                            onTap: onRetry,
                            borderRadius: BorderRadius.circular(6),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Text(
                                '重新生成',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: palette.muted,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
    );

    final avatar = _ChatAvatar(isUser: isUser, palette: palette);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[avatar, const SizedBox(width: 8)],
          Flexible(child: bubble),
          if (isUser) ...[const SizedBox(width: 8), avatar],
        ],
      ),
    );
  }
}

class _ChatAvatar extends StatelessWidget {
  const _ChatAvatar({required this.isUser, required this.palette});

  final bool isUser;
  final AppPalette palette;

  @override
  Widget build(BuildContext context) {
    final colors = isUser
        ? [palette.accent.withValues(alpha: 0.72), palette.accent]
        : [palette.primaryLight, palette.primary];
    return Container(
      width: 30,
      height: 30,
      margin: const EdgeInsets.only(top: 2),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors,
        ),
        borderRadius: BorderRadius.circular(10),
        boxShadow: [
          BoxShadow(
            color: colors.last.withValues(alpha: 0.18),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Icon(
        isUser ? Icons.person_rounded : Icons.auto_awesome,
        size: 15,
        color: Colors.white,
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
