import 'package:flutter/material.dart';

import '../services/voice_session.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class VoiceChatScreen extends StatefulWidget {
  const VoiceChatScreen({super.key});

  @override
  State<VoiceChatScreen> createState() => _VoiceChatScreenState();
}

class _VoiceChatScreenState extends State<VoiceChatScreen> {
  late final VoiceSessionController _voice;
  final ScrollController _scroll = ScrollController();
  String _lastSignature = '';

  @override
  void initState() {
    super.initState();
    _voice = VoiceSessionController()..addListener(_onChanged);
  }

  void _onChanged() {
    final last = _voice.turns.isEmpty ? null : _voice.turns.last;
    final signature =
        '${_voice.turns.length}:${last?.transcript.length ?? 0}:${last?.reply.length ?? 0}:${_voice.phase.name}';
    if (signature == _lastSignature) return;
    _lastSignature = signature;
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
          builder: (context, _) {
            return Column(
              children: [
                PageHeader(
                  kicker: 'Voice',
                  title: '语音对话',
                  subtitle: '连续对话 · 随时打断',
                  actions: [
                    RoundIconButton(
                      icon: Icons.arrow_back_rounded,
                      onTap: () => Navigator.maybePop(context),
                    ),
                  ],
                ),
                Expanded(
                  child: _voice.turns.isEmpty
                      ? _intro(palette)
                      : ListView.builder(
                          controller: _scroll,
                          padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                          itemCount: _voice.turns.length,
                          itemBuilder: (context, index) =>
                              _turn(palette, _voice.turns[index], index),
                        ),
                ),
                _statusRow(palette),
                _controls(palette),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _intro(AppPalette palette) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
      children: [
        Icon(Icons.graphic_eq_rounded, size: 56, color: palette.primary),
        const SizedBox(height: 18),
        Text(
          '像打电话一样对话',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: palette.ink,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          '说完停顿一下，AI 会自动接话；'
          '回答时直接开口就能打断，不用按按钮。',
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
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.headphones_rounded, size: 16, color: palette.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '戴耳机效果最好：外放时 AI 的声音可能被麦克风收进去。'
                  '想打断直接开口说话即可，也可以在下方关闭语音打断。',
                  style: TextStyle(
                    fontSize: 11.5,
                    height: 1.6,
                    color: palette.primary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _turn(AppPalette palette, VoiceTurn turn, int index) {
    final active = index == _voice.turns.length - 1;
    final showReply = turn.reply.isNotEmpty ||
        (active &&
            (_voice.phase == VoicePhase.thinking ||
                _voice.phase == VoicePhase.speaking));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (turn.transcript.isNotEmpty)
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
                turn.transcript,
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.5,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        if (showReply)
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
                    turn.reply.isEmpty ? '…' : turn.reply,
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.6,
                      color: palette.ink,
                    ),
                  ),
                  if (turn.interrupted)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        '已打断',
                        style: TextStyle(
                          fontSize: 10.5,
                          color: palette.muted,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _statusRow(AppPalette palette) {
    final color = _statusColor(palette);
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
              _voice.errorText ??
                  '${_voice.status}${_voice.phase == VoicePhase.thinking || _voice.phase == VoicePhase.speaking ? ' · 直接说话可打断' : ''}',
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

  Color _statusColor(AppPalette palette) {
    switch (_voice.phase) {
      case VoicePhase.recording:
        return palette.primary;
      case VoicePhase.thinking:
        return palette.primaryLight;
      case VoicePhase.speaking:
        return palette.accent;
      case VoicePhase.listening:
        return palette.success;
      case VoicePhase.error:
        return palette.accent;
      case VoicePhase.idle:
        return palette.muted;
    }
  }

  Widget _controls(AppPalette palette) {
    final phase = _voice.phase;
    final idle = phase == VoicePhase.idle || phase == VoicePhase.error;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 10, 24, 22),
      child: Column(
        children: [
          _waveform(palette, phase),
          const SizedBox(height: 12),
          if (!idle)
            GestureDetector(
              onTap: () => _voice.setAutoInterrupt(!_voice.autoInterrupt),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    _voice.autoInterrupt
                        ? Icons.bolt_rounded
                        : Icons.bolt_outlined,
                    size: 15,
                    color: _voice.autoInterrupt
                        ? palette.primary
                        : palette.muted,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    _voice.autoInterrupt ? '语音打断已开启' : '语音打断已关闭',
                    style: TextStyle(
                      fontSize: 11,
                      color: _voice.autoInterrupt
                          ? palette.primary
                          : palette.muted,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 10),
          GestureDetector(
            onTap: () {
              if (idle) {
                _voice.start();
              } else {
                _voice.stop();
              }
            },
            child: Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                color: palette.primary,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: palette.primary.withValues(alpha: 0.3),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Icon(
                idle ? Icons.mic_rounded : Icons.stop_rounded,
                size: 32,
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            idle ? '点击开始语音对话' : '点击结束对话',
            style: TextStyle(fontSize: 11, color: palette.muted),
          ),
        ],
      ),
    );
  }

  Widget _waveform(AppPalette palette, VoicePhase phase) {
    final active = phase != VoicePhase.idle && phase != VoicePhase.error;
    final base = _voice.level;
    final speaking = phase == VoicePhase.speaking;
    return SizedBox(
      height: 34,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: List.generate(9, (index) {
          final distance = (index - 4).abs();
          final factor = 1 - distance * 0.14;
          final height =
              active ? 5 + base * 30 * factor : 4 + distance * 0.6;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 90),
            margin: const EdgeInsets.symmetric(horizontal: 3),
            width: 4,
            height: height.clamp(4.0, 34.0),
            decoration: BoxDecoration(
              color: (speaking ? palette.accent : palette.primary)
                  .withValues(alpha: active ? 0.85 : 0.25),
              borderRadius: BorderRadius.circular(3),
            ),
          );
        }),
      ),
    );
  }
}
