import 'dart:async';

import 'package:flutter/material.dart';

import '../models/vibecoding_models.dart';
import '../services/vibecoding_service.dart';

class VibecodingTaskScreen extends StatefulWidget {
  final VibecodingTask task;
  const VibecodingTaskScreen({super.key, required this.task});

  @override
  State<VibecodingTaskScreen> createState() => _VibecodingTaskScreenState();
}

class _VibecodingTaskScreenState extends State<VibecodingTaskScreen> {
  final VibecodingService _service = VibecodingService();
  final List<String> _milestones = [];
  final List<String> _toolCalls = [];
  final List<String> _fileChanges = [];
  final StringBuffer _output = StringBuffer();
  final ScrollController _scrollController = ScrollController();
  bool _finalOutputShown = false;

  @override
  void initState() {
    super.initState();
    if (widget.task.output.isNotEmpty) {
      _output.write(widget.task.output);
      _finalOutputShown = true;
    }
    _sub = _service.stream.listen(_onMessage);
    _service.ensureConnected();
  }

  StreamSubscription<Map<String, dynamic>>? _sub;

  @override
  void dispose() {
    _sub?.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  void _onMessage(Map<String, dynamic> msg) {
    if (msg['type'] != 'task.event') return;
    if ((msg['task_id'] ?? '').toString() != widget.task.taskId) return;
    final event = (msg['event'] ?? '').toString();
    final data = Map<String, dynamic>.from(msg['data'] ?? {});
    if (!mounted) return;
    setState(() {
      switch (event) {
        case 'milestone':
          final stage = (data['stage'] ?? '').toString();
          if (stage.isNotEmpty) _milestones.add(_stageLabel(stage));
          break;
        case 'output':
          if (_finalOutputShown) break;
          _output.write((data['chunk'] ?? '').toString());
          _trimOutput();
          _scrollToBottom();
          break;
        case 'tool':
          final name = (data['name'] ?? 'tool').toString();
          final detail = (data['detail'] ?? '').toString();
          _toolCalls.add(detail.isEmpty ? name : '$name: $detail');
          break;
        case 'file':
          final path = (data['path'] ?? '').toString();
          final action = (data['action'] ?? '').toString();
          if (path.isNotEmpty) _fileChanges.add('$action $path');
          break;
        case 'done':
          widget.task.status = VibeStatus.done;
          widget.task.durationMs = (data['duration_ms'] as num?)?.toInt();
          final finalOutput = (data['output'] ?? '').toString();
          if (finalOutput.isNotEmpty) {
            _output
              ..clear()
              ..write(finalOutput);
            _finalOutputShown = true;
          }
          _scrollToBottom();
          break;
        case 'failed':
          widget.task.status = VibeStatus.failed;
          widget.task.error = (data['error'] ?? '执行失败').toString();
          break;
      }
      if (event == 'milestone' && (data['stage'] ?? '') == 'cancelled') {
        widget.task.status = VibeStatus.cancelled;
      }
    });
  }

  void _trimOutput() {
    if (_output.length > 200000) {
      final text = _output.toString().substring(_output.length - 150000);
      _output
        ..clear()
        ..write(text);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  String _stageLabel(String stage) {
    switch (stage) {
      case 'spawning':
        return '启动 agent 进程';
      case 'executing':
        return '执行中';
      case 'replying':
        return '生成回复';
      case 'cancelled':
        return '已被取消';
      default:
        return stage;
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final task = widget.task;
    return Scaffold(
      appBar: AppBar(
        title: Text(task.projectName ?? task.project ?? task.taskId,
            style: const TextStyle(fontSize: 16)),
        actions: [
          if (task.isRunning)
            IconButton(
              tooltip: '取消任务',
              icon: const Icon(Icons.stop_circle_outlined),
              onPressed: () => _service.cancelTask(task.taskId),
            ),
        ],
      ),
      body: ListView(
        controller: _scrollController,
        padding: const EdgeInsets.all(16),
        children: [
          _headerCard(scheme, task),
          if (_milestones.isNotEmpty) ..._section(scheme, Icons.timeline, '里程碑',
              _milestones.map((m) => _lineRow(Icons.flag, m, scheme)).toList()),
          if (_toolCalls.isNotEmpty) ..._section(scheme, Icons.construction, '工具调用',
              _toolCalls.map((t) => _lineRow(Icons.terminal, t, scheme)).toList()),
          if (_fileChanges.isNotEmpty) ..._section(scheme, Icons.description_outlined, '文件变更',
              _fileChanges.map((f) => _lineRow(Icons.insert_drive_file_outlined, f, scheme)).toList()),
          ..._section(scheme, Icons.chat_outlined, _outputTitle(task),
              [ _outputCard(scheme) ]),
        ],
      ),
    );
  }

  String _outputTitle(VibecodingTask task) {
    if (_finalOutputShown) return '最终回复';
    return task.isRunning ? '实时输出' : '输出';
  }

  Widget _headerCard(ColorScheme scheme, VibecodingTask task) {
    final status = _statusLabel(task);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _statusIcon(task.status),
                const SizedBox(width: 8),
                Text(status, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                const Spacer(),
                if (task.durationMs != null)
                  Text('${(task.durationMs! / 1000).toStringAsFixed(1)}s',
                      style: TextStyle(fontSize: 12, color: scheme.outline)),
              ],
            ),
            const SizedBox(height: 8),
            Text('${task.tool ?? '?'} · ${task.project ?? ''}',
                style: TextStyle(fontSize: 12, color: scheme.outline)),
            if (task.input.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(task.input, style: const TextStyle(fontSize: 13)),
            ],
            if (task.error != null && task.error!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('❌ ${task.error}', style: const TextStyle(fontSize: 13, color: Colors.red)),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _section(ColorScheme scheme, IconData icon, String title, List<Widget> children) {
    return [
      const SizedBox(height: 16),
      Row(
        children: [
          Icon(icon, size: 16, color: scheme.primary),
          const SizedBox(width: 6),
          Text(title, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: scheme.primary)),
        ],
      ),
      const SizedBox(height: 6),
      ...children,
    ];
  }

  Widget _lineRow(IconData icon, String text, ColorScheme scheme) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 14, color: scheme.outline),
          const SizedBox(width: 6),
          Expanded(child: SelectableText(text, style: const TextStyle(fontSize: 12))),
        ],
      ),
    );
  }

  Widget _outputCard(ColorScheme scheme) {
    final text = _output.toString().trim();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: SizedBox(
          width: double.infinity,
          child: text.isEmpty
              ? Text(taskRunningHint(),
                  style: TextStyle(fontSize: 12, color: scheme.outline))
              : SelectableText(text, style: const TextStyle(fontSize: 13, height: 1.4)),
        ),
      ),
    );
  }

  String taskRunningHint() {
    if (widget.task.status == VibeStatus.pending) return '等待桌面设备认领任务…';
    return '暂无输出，等待 agent 执行…';
  }

  String _statusLabel(VibecodingTask task) {
    switch (task.status) {
      case VibeStatus.pending:
        return '待执行';
      case VibeStatus.running:
        return '运行中';
      case VibeStatus.done:
        return '已完成';
      case VibeStatus.failed:
        return '失败';
      case VibeStatus.cancelled:
        return '已取消';
      default:
        return '未知';
    }
  }

  Widget _statusIcon(VibeStatus status) {
    switch (status) {
      case VibeStatus.running:
      case VibeStatus.pending:
        return const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      case VibeStatus.done:
        return const Icon(Icons.check_circle, color: Colors.green, size: 18);
      case VibeStatus.failed:
        return const Icon(Icons.error, color: Colors.red, size: 18);
      case VibeStatus.cancelled:
        return const Icon(Icons.cancel, color: Colors.orange, size: 18);
      default:
        return const Icon(Icons.help_outline, size: 18);
    }
  }
}
