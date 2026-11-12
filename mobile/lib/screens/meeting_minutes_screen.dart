import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../services/api_service.dart';
import '../services/file_transfer_service.dart';
import '../services/meeting_job_monitor.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'notes_screen.dart';

/// Record a meeting, upload the original file to MinIO once, then reference
/// that object from a server-side transcription job. Audio is retained until
/// the user explicitly deletes the minutes.
class MeetingMinutesScreen extends StatefulWidget {
  const MeetingMinutesScreen({super.key, this.onOpenNote});

  final void Function(int noteId, String title)? onOpenNote;

  @override
  State<MeetingMinutesScreen> createState() => _MeetingMinutesScreenState();
}

class _MeetingMinutesScreenState extends State<MeetingMinutesScreen>
    with WidgetsBindingObserver {
  final _recorder = AudioRecorder();
  final _titleController = TextEditingController();
  Timer? _timer;
  Timer? _poll;
  int _pollFailures = 0;
  Duration _elapsed = Duration.zero;
  bool _recording = false;
  bool _paused = false;
  bool _busy = false;
  bool _stopping = false;
  bool _manualPause = false;
  double _uploadProgress = 0;
  String _statusText = '';
  String _error = '';
  String? _recordingPath;
  StreamSubscription<RecordState>? _recordStateSub;
  Map<String, dynamic>? _job;
  List<Map<String, dynamic>> _history = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _recordStateSub = _recorder.onStateChanged().listen(
          _onRecorderState,
          onError: (_) {},
        );
    _loadHistory();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _poll?.cancel();
    _recordStateSub?.cancel();
    if (_recording) {
      // Make sure the last audio chunk is flushed even when the route is
      // removed programmatically without going through the back handler.
      _recorder.stop().catchError((_) => null);
    }
    _recorder.dispose();
    _titleController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _recording) {
      _recorder.isRecording().then((active) {
        if (!active && mounted && _recording && !_stopping) {
          _stopAndCreate(interrupted: true);
        }
      }).catchError((_) {});
    }
  }

  void _onRecorderState(RecordState state) {
    if (!mounted || !_recording || _stopping) return;
    if (state == RecordState.stop) {
      // The OS may stop the audio session for a call or another app. Give
      // the plugin a moment to flush the file, then save what we have.
      Future<void>.delayed(const Duration(milliseconds: 350), () {
        if (mounted && _recording && !_stopping) {
          _stopAndCreate(interrupted: true);
        }
      });
    } else if (state == RecordState.pause && !_manualPause) {
      setState(() => _paused = true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('录音被系统暂停，已暂停录音'),
          action: SnackBarAction(label: '继续', onPressed: _pauseResume),
        ),
      );
    } else if (state == RecordState.record && _paused && !_manualPause) {
      setState(() => _paused = false);
    }
  }

  Future<void> _handleBack() async {
    if (!_recording) {
      Navigator.maybePop(context);
      return;
    }
    final save = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('正在录音'),
        content: const Text('结束录音并保存已录内容？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('继续录音'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('结束并保存'),
          ),
        ],
      ),
    );
    if (save == true && mounted) {
      await _stopAndCreate();
      if (mounted) Navigator.maybePop(context);
    }
  }

  Future<void> _loadHistory() async {
    try {
      final items = await ApiService().listMeetingMinutes(limit: 10);
      if (!mounted) return;
      setState(() => _history = items);
    } catch (_) {
      // History is best-effort; recording stays available offline.
    }
  }

  Future<void> _openHistory(Map<String, dynamic> item) async {
    final id = (item['id'] as num?)?.toInt();
    if (id == null) return;
    setState(() {
      _busy = true;
      _statusText = '正在加载纪要…';
      _error = '';
    });
    try {
      final job = await ApiService().getMeetingMinutes(id);
      if (!mounted) return;
      setState(() {
        _job = job;
        _busy = false;
        _statusText = '';
        _elapsed = Duration.zero;
      });
      final status = (job['status'] ?? '').toString();
      if (status != 'done' && status != 'failed') _startPolling(id);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _statusText = '';
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  String _historyTime(dynamic raw) {
    final dt = DateTime.tryParse('${raw ?? ''}')?.toLocal();
    if (dt == null) return '';
    return '${dt.month}/${dt.day} '
        '${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }

  String _jobAge(Map<String, dynamic> job) {
    final raw = job['started_at'] ?? job['created_at'];
    final started = DateTime.tryParse('${raw ?? ''}')?.toLocal();
    if (started == null) return '';
    final diff = DateTime.now().difference(started);
    if (diff.inSeconds < 60) return '${diff.inSeconds} 秒';
    if (diff.inMinutes < 60) {
      return '${diff.inMinutes} 分 ${diff.inSeconds.remainder(60)} 秒';
    }
    return '${diff.inHours} 小时 ${diff.inMinutes.remainder(60)} 分';
  }

  String _stamp() {
    final now = DateTime.now();
    return '${now.year}${now.month.toString().padLeft(2, '0')}'
        '${now.day.toString().padLeft(2, '0')}_'
        '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
  }

  String _fmt(Duration d) {
    final h = d.inHours;
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return h > 0 ? '$h:$m:$s' : '$m:$s';
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
    if (_busy) return;
    try {
      if (!await _recorder.hasPermission()) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('需要麦克风权限才能录音')),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      final path = '${dir.path}/meeting_${_stamp()}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc),
        path: path,
      );
      if (!mounted) return;
      _recordingPath = path;
      _stopping = false;
      _manualPause = false;
      setState(() {
        _recording = true;
        _paused = false;
        _elapsed = Duration.zero;
        _error = '';
        _job = null;
        _uploadProgress = 0;
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
        _manualPause = true;
        try {
          await _recorder.pause();
        } finally {
          _manualPause = false;
        }
        if (mounted) setState(() => _paused = true);
      }
    } catch (_) {}
  }

  Future<void> _stopAndCreate({bool interrupted = false}) async {
    if (!_recording || _stopping) return;
    _stopping = true;
    _timer?.cancel();
    String? path;
    try {
      path = await _recorder.stop();
    } catch (_) {}
    path ??= _recordingPath;
    _recordingPath = null;
    _stopping = false;
    if (!mounted) return;
    setState(() {
      _recording = false;
      _paused = false;
      _busy = true;
      _statusText = '正在上传录音…';
    });
    if (path == null) {
      setState(() {
        _busy = false;
        _statusText = '';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('没有录到声音')),
      );
      return;
    }
    final audioFile = File(path);
    if (!await audioFile.exists() || await audioFile.length() == 0) {
      if (mounted) {
        setState(() {
          _busy = false;
          _statusText = '';
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('录音文件为空，未能保存')),
        );
      }
      return;
    }
    if (interrupted && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('录音被系统中断，已自动保存已录部分')),
      );
    }

    final filename = '会议录音_${_stamp()}.m4a';
    final title = _titleController.text.trim();
    try {
      final uploaded = await FileTransferService().upload(
        path,
        filename,
        '/',
        onProgress: (sent, total) {
          if (!mounted || total <= 0) return;
          setState(() => _uploadProgress = sent / total);
        },
      );
      final fileId = (uploaded['id'] as num?)?.toInt();
      if (fileId == null) throw Exception('上传结果缺少文件 ID');
      try {
        await File(path).delete();
      } catch (_) {}

      if (mounted) {
        setState(() {
          _uploadProgress = 1;
          _statusText = '正在创建转写任务…';
        });
      }
      final job = await ApiService().createMeetingMinutes(
        fileId: fileId,
        title: title.isEmpty ? null : title,
      );
      final jobId = (job['id'] as num?)?.toInt();
      if (jobId != null) {
        MeetingJobMonitor().track(
          jobId,
          title: (job['title'] ?? '会议纪要').toString(),
        );
      }
      if (!mounted) return;
      setState(() {
        _job = job;
        _busy = false;
        _statusText = '';
      });
      if (jobId != null) _startPolling(jobId);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _statusText = '';
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _startPolling(int id) {
    MeetingJobMonitor().track(
      id,
      title: (_job?['title'] ?? '会议纪要').toString(),
    );
    _poll?.cancel();
    _pollFailures = 0;
    _poll = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final job = await ApiService().getMeetingMinutes(id);
        if (!mounted) return;
        _pollFailures = 0;
        setState(() => _job = job);
        final status = (job['status'] ?? '').toString();
        if (status == 'done' || status == 'failed') {
          _poll?.cancel();
          _loadHistory();
        }
      } catch (_) {
        _pollFailures += 1;
        if (_pollFailures >= 5 && mounted) {
          _poll?.cancel();
          setState(() {
            _error = '无法获取处理状态，请检查网络后重试';
          });
        }
      }
    });
  }

  Future<void> _retry() async {
    final id = (_job?['id'] as num?)?.toInt();
    if (id == null) return;
    try {
      await ApiService().retryMeetingMinutes(id);
      _startPolling(id);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('重试失败: $e')),
      );
    }
  }

  Future<void> _delete() async {
    final id = (_job?['id'] as num?)?.toInt();
    if (id == null) return;
    final deleteAudio = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除会议纪要？'),
        content: const Text('默认同时删除录音文件。也可以只删除纪要，保留录音。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('保留录音'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('一起删除'),
          ),
        ],
      ),
    );
    if (deleteAudio == null || !mounted) return;
    try {
      await ApiService().deleteMeetingMinutes(id, deleteAudio: deleteAudio);
      MeetingJobMonitor().untrack(id);
      if (!mounted) return;
      setState(() {
        _job = null;
        _elapsed = Duration.zero;
        _titleController.clear();
      });
      _loadHistory();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('会议纪要已删除')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('删除失败: $e')),
      );
    }
  }

  void _openNote() {
    final noteId = (_job?['note_id'] as num?)?.toInt();
    final title = (_job?['title'] ?? '会议纪要').toString();
    if (noteId == null) return;
    final open = widget.onOpenNote;
    if (open != null) {
      open(noteId, title);
    } else {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const NotesScreen()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final status = (_job?['status'] ?? '').toString();
    return PopScope(
      canPop: !_recording,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _recording) _handleBack();
      },
      child: Scaffold(
        backgroundColor: palette.background,
        body: SafeArea(
          child: Column(
            children: [
              PageHeader(
                kicker: 'Minutes',
                title: '录音纪要',
                subtitle: '录音只上传一次，原文件默认保留',
                actions: [
                  RoundIconButton(
                    icon: Icons.arrow_back_rounded,
                    onTap: _handleBack,
                  ),
                ],
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  children: [
                    if (_job == null && !_busy) _buildRecorder(palette),
                    if (_job == null && !_busy) ...[
                      const SizedBox(height: 12),
                      _buildHistory(palette),
                    ],
                    if (_busy) _buildBusy(palette),
                    if (_job != null && !_busy) _buildJob(palette, status),
                    if (_error.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      if (_job != null) InlineErrorBanner(onRetry: _retry),
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          _error,
                          style: TextStyle(fontSize: 11, color: palette.muted),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRecorder(AppPalette palette) {
    return Column(
      children: [
        AppCard(
          child: TextField(
            controller: _titleController,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(
              hintText: '会议主题（可选）',
              prefixIcon: Icon(Icons.title_rounded, size: 18),
            ),
          ),
        ),
        const SizedBox(height: 12),
        AppCard(
          child: Column(
            children: [
              Container(
                width: 140,
                height: 140,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: palette.primarySoft,
                  border: Border.all(
                    color: _recording ? palette.accent : palette.line,
                    width: 2,
                  ),
                ),
                alignment: Alignment.center,
                child: Text(
                  _fmt(_elapsed),
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    color: _recording ? palette.accent : palette.ink,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                _recording ? (_paused ? '已暂停' : '正在录音…') : '点击开始录音',
                style: TextStyle(fontSize: 12, color: palette.muted),
              ),
              if (_recording) ...[
                const SizedBox(height: 5),
                Text(
                  '锁屏后仍会继续录音；来电或系统中断会自动保存已录部分。',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 10, color: palette.muted),
                ),
              ],
              const SizedBox(height: 18),
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
                          onPressed: _stopAndCreate,
                          icon: const Icon(Icons.stop_rounded, size: 20),
                          label: const Text('结束并生成纪要'),
                        )
                      : FilledButton.icon(
                          onPressed: _start,
                          icon: const Icon(Icons.mic_rounded, size: 20),
                          label: const Text('开始录音'),
                        ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        AppCard(
          color: palette.primarySoft,
          borderColor: Colors.transparent,
          child: Text(
            '录音会直接上传到你的 MinIO，再由服务器引用该文件转写，不会重复上传。'
            '转写完成后录音默认保留，可在删除纪要时选择是否一并删除。',
            style: TextStyle(
              fontSize: 11,
              height: 1.65,
              color: palette.ink.withValues(alpha: 0.78),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHistory(AppPalette palette) {
    if (_history.isEmpty) return const SizedBox.shrink();
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '最近纪要',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 1,
              fontWeight: FontWeight.w700,
              color: palette.muted,
            ),
          ),
          const SizedBox(height: 4),
          for (var i = 0; i < _history.length; i++) ...[
            if (i > 0)
              Divider(height: 12, color: palette.line.withValues(alpha: 0.8)),
            InkWell(
              onTap: () => _openHistory(_history[i]),
              borderRadius: BorderRadius.circular(10),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(
                  children: [
                    Container(
                      width: 30,
                      height: 30,
                      decoration: BoxDecoration(
                        color: palette.primarySoft,
                        borderRadius: BorderRadius.circular(9),
                      ),
                      child: Icon(
                        Icons.graphic_eq_rounded,
                        size: 16,
                        color: palette.primary,
                      ),
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            (_history[i]['title'] ?? '会议纪要').toString(),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: palette.ink,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${_statusLabel((_history[i]['status'] ?? '').toString())}'
                            ' · ${_historyTime(_history[i]['created_at'])}',
                            style: TextStyle(
                              fontSize: 9.5,
                              color: palette.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 16,
                      color: palette.muted,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildBusy(AppPalette palette) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _statusText.isEmpty ? '处理中…' : _statusText,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: palette.ink,
            ),
          ),
          const SizedBox(height: 12),
          if (_uploadProgress > 0 && _uploadProgress < 1) ...[
            LinearProgressIndicator(
              value: _uploadProgress,
              color: palette.primary,
              backgroundColor: palette.primarySoft,
            ),
            const SizedBox(height: 6),
            Text(
              '上传 ${(_uploadProgress * 100).toStringAsFixed(0)}%',
              style: TextStyle(fontSize: 10, color: palette.muted),
            ),
          ] else
            LinearProgressIndicator(
              color: palette.primary,
              backgroundColor: palette.primarySoft,
            ),
        ],
      ),
    );
  }

  Widget _buildJob(AppPalette palette, String status) {
    final job = _job!;
    final minutes = job['minutes'] is Map
        ? (job['minutes'] as Map).map((k, v) => MapEntry(k.toString(), v))
        : <String, dynamic>{};
    final done = status == 'done';
    final failed = status == 'failed';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AppCard(
          child: Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: failed
                      ? palette.accent.withValues(alpha: 0.12)
                      : palette.primarySoft,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  failed ? Icons.error_outline : Icons.graphic_eq_rounded,
                  size: 18,
                  color: failed ? palette.accent : palette.primary,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      (job['title'] ?? '会议纪要').toString(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: palette.ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _statusLabel(status),
                      style: TextStyle(
                        fontSize: 10.5,
                        color: failed ? palette.accent : palette.muted,
                      ),
                    ),
                    if (!done && !failed)
                      Text(
                        '已等待 ${_jobAge(job)} · MOSS 长录音通常需要几分钟',
                        style: TextStyle(
                          fontSize: 9.5,
                          color: palette.muted,
                        ),
                      ),
                  ],
                ),
              ),
              if (!done && !failed)
                CircularProgressIndicator(
                  strokeWidth: 2,
                  color: palette.primary,
                ),
            ],
          ),
        ),
        if (failed) ...[
          const SizedBox(height: 10),
          AppCard(
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    (job['error'] ?? '转写失败').toString(),
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                ),
                TextButton(onPressed: _retry, child: const Text('重试')),
              ],
            ),
          ),
        ],
        if (done) ...[
          const SizedBox(height: 10),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '摘要',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 0.6,
                    fontWeight: FontWeight.w800,
                    color: palette.muted,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  (minutes['summary'] ?? '纪要已生成，打开笔记查看完整内容。').toString(),
                  style: TextStyle(
                    fontSize: 12.5,
                    height: 1.7,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 10),
                _minuteSection(palette, '关键讨论', minutes['discussion']),
                _minuteSection(palette, '决议', minutes['decisions']),
                _minutesActions(palette, minutes['action_items']),
                _minuteSection(palette, '风险与遗留', minutes['risks']),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _openNote,
                  icon: const Icon(Icons.article_outlined, size: 17),
                  label: const Text('打开笔记'),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: _delete,
                child: const Text('删除纪要'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '录音已保留在文件中；删除纪要时可选择一并删除音频。',
            style: TextStyle(fontSize: 10, color: palette.muted),
          ),
        ],
      ],
    );
  }

  String _statusLabel(String status) {
    return switch (status) {
      'queued' => '排队中，等待转写',
      'transcribing' => '正在转写录音',
      'summarizing' => '正在生成会议纪要',
      'done' => '纪要已生成',
      'failed' => '处理失败',
      _ => '处理中',
    };
  }

  Widget _minuteSection(AppPalette palette, String title, dynamic value) {
    final items = value is List
        ? value.map((e) => e.toString()).where((e) => e.isNotEmpty).toList()
        : <String>[];
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 0.6,
              fontWeight: FontWeight.w800,
              color: palette.muted,
            ),
          ),
          const SizedBox(height: 4),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: TagDot(color: palette.primary, size: 4),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      item,
                      style: TextStyle(
                        fontSize: 12,
                        height: 1.6,
                        color: palette.ink,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _minutesActions(AppPalette palette, dynamic value) {
    final items = value is List ? value : const [];
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '待办',
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 0.6,
              fontWeight: FontWeight.w800,
              color: palette.muted,
            ),
          ),
          const SizedBox(height: 4),
          for (final item in items)
            if (item is Map)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.check_box_outline_blank_rounded,
                      size: 15,
                      color: palette.primary,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        '${item['title'] ?? ''}'
                        '${(item['owner'] ?? '').toString().isEmpty ? '' : ' · ${item['owner']}'}'
                        '${(item['due'] ?? '').toString().isEmpty ? '' : ' · ${item['due']}'}',
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.6,
                          color: palette.ink,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}
