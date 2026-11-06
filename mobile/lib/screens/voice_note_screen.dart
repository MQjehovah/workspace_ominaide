import 'dart:async';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../services/notes_import_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Record a voice note, send it to the backend for transcription, and open the
/// generated note.
class VoiceNoteScreen extends StatefulWidget {
  const VoiceNoteScreen({super.key, required this.onOpenNote});

  final void Function(int noteId, String title) onOpenNote;

  @override
  State<VoiceNoteScreen> createState() => _VoiceNoteScreenState();
}

class _VoiceNoteScreenState extends State<VoiceNoteScreen> {
  final _recorder = AudioRecorder();
  Timer? _timer;
  Duration _elapsed = Duration.zero;
  bool _recording = false;
  bool _paused = false;
  bool _processing = false;

  @override
  void dispose() {
    _timer?.cancel();
    _recorder.dispose();
    super.dispose();
  }

  String _stamp() {
    final now = DateTime.now();
    return '${now.year}${now.month.toString().padLeft(2, '0')}'
        '${now.day.toString().padLeft(2, '0')}_'
        '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && !_paused) {
        setState(() => _elapsed += const Duration(seconds: 1));
      }
    });
  }

  Future<void> _start() async {
    if (_processing) return;
    try {
      if (!await _recorder.hasPermission()) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('需要麦克风权限才能录音')),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      final path = '${dir.path}/voice_note_${_stamp()}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc),
        path: path,
      );
      if (!mounted) return;
      setState(() {
        _recording = true;
        _paused = false;
        _elapsed = Duration.zero;
      });
      _startTimer();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('录音失败: $e')),
      );
    }
  }

  Future<void> _pauseResume() async {
    if (!_recording) return;
    try {
      if (_paused) {
        await _recorder.resume();
        if (mounted) setState(() => _paused = false);
      } else {
        await _recorder.pause();
        if (mounted) setState(() => _paused = true);
      }
    } catch (_) {}
  }

  Future<void> _stopAndTranscribe() async {
    if (!_recording) return;
    _timer?.cancel();
    String? path;
    try {
      path = await _recorder.stop();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _recording = false;
      _paused = false;
      _processing = true;
    });
    if (path == null) {
      setState(() => _processing = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('没有录到声音')),
      );
      return;
    }
    try {
      final stamp = _stamp();
      final data = await NotesImportService().importFile(
        path,
        'voice_note_$stamp.m4a',
        title: '语音笔记 $stamp',
      );
      if (!mounted) return;
      final id = (data['id'] as num?)?.toInt();
      final title = (data['title'] ?? '语音笔记').toString();
      Navigator.pop(context);
      if (id != null) widget.onOpenNote(id, title);
    } catch (e) {
      if (!mounted) return;
      setState(() => _processing = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
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
              kicker: 'Voice Note',
              title: '语音笔记',
              subtitle: '录音后自动转写并生成笔记',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 150,
                        height: 150,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: palette.primarySoft,
                          border: Border.all(
                            color: _recording ? palette.accent : palette.line,
                            width: 2,
                          ),
                        ),
                        child: Center(
                          child: Text(
                            _fmt(_elapsed),
                            style: TextStyle(
                              fontSize: 30,
                              fontWeight: FontWeight.w800,
                              color: _recording ? palette.accent : palette.ink,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Text(
                        _processing
                            ? '正在转写并生成笔记…'
                            : _recording
                                ? (_paused ? '已暂停' : '正在录音…')
                                : '点击下方按钮开始录音',
                        style: TextStyle(fontSize: 12, color: palette.muted),
                      ),
                      const SizedBox(height: 28),
                      if (_processing)
                        const CircularProgressIndicator()
                      else
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            if (_recording) ...[
                              OutlinedButton.icon(
                                onPressed: _pauseResume,
                                icon: Icon(
                                  _paused ? Icons.play_arrow : Icons.pause,
                                  size: 18,
                                ),
                                label: Text(_paused ? '继续' : '暂停'),
                              ),
                              const SizedBox(width: 12),
                            ],
                            _recording
                                ? FilledButton.icon(
                                    onPressed: _stopAndTranscribe,
                                    icon: const Icon(Icons.stop_rounded, size: 20),
                                    label: const Text('结束并转写'),
                                  )
                                : FilledButton.icon(
                                    onPressed: _start,
                                    icon: const Icon(Icons.mic_rounded, size: 20),
                                    label: const Text('开始录音'),
                                  ),
                          ],
                        ),
                      const SizedBox(height: 34),
                      AppCard(
                        child: Text(
                          '录音会上传到你的 OmniAide 服务器进行转写，不会发送给第三方。'
                          '单个文件限制 25MB（约 25 分钟），更长的会议建议分段录制。',
                          style: TextStyle(
                            fontSize: 11,
                            height: 1.6,
                            color: palette.muted,
                          ),
                        ),
                      ),
                    ],
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
