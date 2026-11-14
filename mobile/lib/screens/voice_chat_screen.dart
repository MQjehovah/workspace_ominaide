import 'dart:async';

import 'package:flutter/material.dart';

import '../services/realtime_voice.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class VoiceChatScreen extends StatefulWidget {
  const VoiceChatScreen({super.key});

  @override
  State<VoiceChatScreen> createState() => _VoiceChatScreenState();
}

class _VoiceChatScreenState extends State<VoiceChatScreen> {
  late final RealtimeVoiceController _voice;
  final ScrollController _scroll = ScrollController();
  String _signature = '';

  @override
  void initState() {
    super.initState();
    _voice = RealtimeVoiceController()..addListener(_onChanged);
  }

  void _onChanged() {
    final sig =
        '${_voice.turns.length}:${_voice.userText.length}:${_voice.assistantText.length}:${_voice.state.name}';
    if (sig == _signature) return;
    _signature = sig;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  void dispose() {
    _voice.removeListener(_onChanged);
    unawaited(_voice.close());
    _voice.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: AnimatedBuilder(
          animation: _voice,
          builder: (context, _) => Column(
            children: [
              PageHeader(
                kicker: 'MOSS-Live',
                title: '语音对话',
                subtitle: '全双工实时对话 · 直接说话即可打断',
                actions: [
                  RoundIconButton(
                    icon: Icons.arrow_back_rounded,
                    onTap: () => Navigator.maybePop(context),
                  ),
                ],
              ),
              Expanded(
                child: _voice.turns.isEmpty &&
                        _voice.userText.isEmpty &&
                        _voice.assistantText.isEmpty
                    ? _intro(palette)
                    : _conversation(palette),
              ),
              _statusRow(palette),
              _controls(palette),
            ],
          ),
        ),
      ),
    );
  }

  Widget _intro(AppPalette palette) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 40, 24, 24),
      children: [
        Icon(Icons.graphic_eq_rounded, size: 56, color: palette.primary),
        const SizedBox(height: 16),
        Text(
          '像打电话一样自然',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: palette.ink,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          '点击下方麦克风开始。MOSS 会边听边说，'
          '你随时开口就能打断；不需要按任何按钮。',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12.5, height: 1.7, color: palette.muted),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: palette.primarySoft,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            '实时语音会持续上传麦克风，包括停顿时的静音。'
            '建议戴耳机，外放时回声可能影响识别。',
            style: TextStyle(
              fontSize: 11.5,
              height: 1.6,
              color: palette.primary,
            ),
          ),
        ),
      ],
    );
  }

  Widget _conversation(AppPalette palette) {
    final items = <Widget>[];
    for (final turn in _voice.turns) {
      items.addAll(_bubbles(palette, turn.user, turn.assistant, turn.interrupted));
    }
    if (_voice.userText.isNotEmpty || _voice.assistantText.isNotEmpty) {
      items.addAll(_bubbles(
        palette,
        _voice.userText,
        _voice.assistantText,
        false,
        live: true,
      ));
    }
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      children: items,
    );
  }

  List<Widget> _bubbles(
    AppPalette palette,
    String user,
    String assistant,
    bool interrupted, {
    bool live = false,
  }) {
    return [
      if (user.isNotEmpty)
        Align(
          alignment: Alignment.centerRight,
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(12),
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.78,
            ),
            decoration: BoxDecoration(
              color: palette.primary,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              user,
              style: const TextStyle(
                fontSize: 13,
                height: 1.5,
                color: Colors.white,
              ),
            ),
          ),
        ),
      if (assistant.isNotEmpty || (live && _voice.speaking))
        Align(
          alignment: Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.all(12),
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.82,
            ),
            decoration: BoxDecoration(
              color: palette.card,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: palette.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  assistant.isEmpty ? '…' : assistant,
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.6,
                    color: palette.ink,
                  ),
                ),
                if (interrupted)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      '被打断',
                      style: TextStyle(fontSize: 10.5, color: palette.muted),
                    ),
                  ),
              ],
            ),
          ),
        ),
    ];
  }

  Widget _statusRow(AppPalette palette) {
    final color = switch (_voice.state) {
      RealtimeVoiceState.live => palette.success,
      RealtimeVoiceState.ready => palette.primaryLight,
      RealtimeVoiceState.connecting => palette.primary,
      RealtimeVoiceState.failed => palette.accent,
      _ => palette.muted,
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 4, 24, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              _voice.errorText ?? _voice.status,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11.5,
                color: _voice.errorText != null ? palette.accent : palette.muted,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _controls(AppPalette palette) {
    final active = _voice.active;
    final failed = _voice.state == RealtimeVoiceState.failed;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 10, 24, 22),
      child: Column(
        children: [
          _waveform(palette, active),
          const SizedBox(height: 12),
          if (active)
            Text(
              '直接开口说话即可打断',
              style: TextStyle(
                fontSize: 11,
                color: _voice.speaking ? palette.accent : palette.muted,
              ),
            ),
          const SizedBox(height: 10),
          GestureDetector(
            onTap: () {
              if (active) {
                _voice.close();
              } else {
                _voice.connect();
              }
            },
            child: Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                color: active ? palette.accent : palette.primary,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: (active ? palette.accent : palette.primary)
                        .withValues(alpha: 0.3),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Icon(
                active ? Icons.call_end_rounded : Icons.mic_rounded,
                size: 32,
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            active
                ? '点击结束通话'
                : failed
                    ? '连接失败，点击重试'
                    : '点击开始语音通话',
            style: TextStyle(fontSize: 11, color: palette.muted),
          ),
        ],
      ),
    );
  }

  Widget _waveform(AppPalette palette, bool active) {
    return SizedBox(
      height: 34,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(9, (index) {
          final distance = (index - 4).abs();
          final factor = 1 - distance * 0.14;
          final boost = _voice.speaking ? 1.0 : 0.35;
          final height = active ? 6 + 20 * factor * boost : 4 + distance * 0.6;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            margin: const EdgeInsets.symmetric(horizontal: 3),
            width: 4,
            height: height.clamp(4.0, 30.0),
            decoration: BoxDecoration(
              color: (active
                      ? (_voice.speaking ? palette.accent : palette.primary)
                      : palette.muted)
                  .withValues(alpha: active ? 0.8 : 0.25),
              borderRadius: BorderRadius.circular(3),
            ),
          );
        }),
      ),
    );
  }
}
