import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../services/voice_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class VoiceChatScreen extends StatefulWidget {
  const VoiceChatScreen({super.key});

  @override
  State<VoiceChatScreen> createState() => _VoiceChatScreenState();
}

class _VoiceChatScreenState extends State<VoiceChatScreen> {
  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  final _turns = <_VoiceTurn>[];

  bool _recording = false;
  bool _processing = false;
  String _status = '点击下方按钮开始说话';

  @override
  void dispose() {
    _recorder.dispose();
    _player.dispose();
    super.dispose();
  }

  Future<void> _toggleRecording() async {
    if (_processing) return;
    if (_recording) {
      await _stopAndSend();
      return;
    }
    try {
      if (!await _recorder.hasPermission()) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('需要麦克风权限才能语音对话')),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      final path =
          '${dir.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc),
        path: path,
      );
      if (!mounted) return;
      setState(() {
        _recording = true;
        _status = '正在录音，再次点击结束';
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('录音失败: $e')),
      );
    }
  }

  Future<void> _stopAndSend() async {
    String? path;
    try {
      path = await _recorder.stop();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _recording = false;
      _processing = true;
      _status = '正在识别并生成回复…';
    });
    if (path == null) {
      setState(() {
        _processing = false;
        _status = '没有录到声音，再试一次';
      });
      return;
    }
    try {
      final result = await VoiceService().sendVoice(File(path));
      if (!mounted) return;
      final dir = await getTemporaryDirectory();
      final ext = result.mimeType.contains('mpeg') || result.mimeType.contains('mp3')
          ? 'mp3'
          : 'wav';
      final audioFile = File(
        '${dir.path}/voice_reply_${DateTime.now().millisecondsSinceEpoch}.$ext',
      );
      await audioFile.writeAsBytes(result.audio);
      await _player.play(DeviceFileSource(audioFile.path));
      if (!mounted) return;
      setState(() {
        _turns.add(_VoiceTurn(
          transcript: result.transcript,
          reply: result.reply,
        ));
        _processing = false;
        _status = '点击下方按钮继续说话';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _processing = false;
        _status = '语音对话失败';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
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
              kicker: 'Voice',
              title: '语音对话',
              subtitle: '说话，AI 用语音回答',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: _turns.isEmpty
                  ? ListView(
                      padding: const EdgeInsets.fromLTRB(24, 60, 24, 24),
                      children: [
                        Icon(
                          Icons.graphic_eq_rounded,
                          size: 56,
                          color: palette.primary,
                        ),
                        const SizedBox(height: 18),
                        Text(
                          '像打电话一样和 OmniAide 对话',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: palette.ink,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '点击下方麦克风开始录音，再点一次结束并发送。'
                          '需要后端配置 ASR 与 TTS。',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 12,
                            height: 1.6,
                            color: palette.muted,
                          ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                      itemCount: _turns.length,
                      itemBuilder: (context, index) {
                        final turn = _turns[index];
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
                                    maxWidth:
                                        MediaQuery.of(context).size.width * 0.78,
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
                            if (turn.reply.isNotEmpty)
                              Align(
                                alignment: Alignment.centerLeft,
                                child: Container(
                                  margin: const EdgeInsets.only(bottom: 16),
                                  padding: const EdgeInsets.all(12),
                                  constraints: BoxConstraints(
                                    maxWidth:
                                        MediaQuery.of(context).size.width * 0.82,
                                  ),
                                  decoration: BoxDecoration(
                                    color: palette.card,
                                    borderRadius: BorderRadius.circular(14),
                                    border: Border.all(color: palette.line),
                                  ),
                                  child: Text(
                                    turn.reply,
                                    style: TextStyle(
                                      fontSize: 13,
                                      height: 1.6,
                                      color: palette.ink,
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        );
                      },
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
              child: Column(
                children: [
                  Text(
                    _status,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11.5, color: palette.muted),
                  ),
                  const SizedBox(height: 12),
                  GestureDetector(
                    onTap: _toggleRecording,
                    child: Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        color: _recording ? palette.accent : palette.primary,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: (_recording ? palette.accent : palette.primary)
                                .withValues(alpha: 0.3),
                            blurRadius: 24,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: _processing
                          ? const Padding(
                              padding: EdgeInsets.all(24),
                              child: CircularProgressIndicator(
                                strokeWidth: 3,
                                color: Colors.white,
                              ),
                            )
                          : Icon(
                              _recording
                                  ? Icons.stop_rounded
                                  : Icons.mic_rounded,
                              size: 34,
                              color: Colors.white,
                            ),
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

class _VoiceTurn {
  final String transcript;
  final String reply;

  const _VoiceTurn({required this.transcript, required this.reply});
}
