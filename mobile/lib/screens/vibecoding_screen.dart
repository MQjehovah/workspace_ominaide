import 'dart:async';
import 'dart:collection';

import 'package:flutter/material.dart';

import '../models/vibecoding_models.dart';
import '../services/api_service.dart';
import '../services/vibecoding_service.dart';
import 'vibecoding_task_screen.dart';

class VibecodingScreen extends StatefulWidget {
  const VibecodingScreen({super.key});
  @override
  State<VibecodingScreen> createState() => _VibecodingScreenState();
}

class _VibecodingScreenState extends State<VibecodingScreen> {
  final VibecodingService _service = VibecodingService();
  StreamSubscription<Map<String, dynamic>>? _sub;

  final LinkedHashMap<String, VibecodingTask> _tasks = LinkedHashMap();
  List<VibecodingDevice> _devices = [];
  List<VibecodingProject> _projects = [];
  Map<String, bool> _tools = {};
  String _selectedTool = 'opencode';
  String? _selectedProject;
  bool _projectsRequested = false;
  final _inputController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadRestTasks();
    _sub = _service.stream.listen(_onMessage);
    _service.ensureConnected();
    _service.connected.addListener(_onConnectedChanged);
  }

  @override
  void dispose() {
    _service.connected.removeListener(_onConnectedChanged);
    _sub?.cancel();
    _inputController.dispose();
    super.dispose();
  }

  void _onConnectedChanged() {
    if (!mounted) return;
    setState(() {});
    if (_service.connected.value && !_projectsRequested) {
      _projectsRequested = true;
      _service.requestProjects(requestId: 'proj-${DateTime.now().millisecondsSinceEpoch}');
    }
  }

  Future<void> _loadRestTasks() async {
    final raw = await ApiService().listVibecodingTasks();
    if (!mounted) return;
    setState(() {
      for (final item in raw) {
        if (item is Map) {
          final t = VibecodingTask.fromJson(Map<String, dynamic>.from(item));
          _tasks[t.taskId] = t;
        }
      }
    });
  }

  void _onMessage(Map<String, dynamic> msg) {
    if (!mounted) return;
    switch (msg['type']) {
      case 'device.status':
        setState(() {
          _devices = ((msg['devices'] as List?) ?? [])
              .whereType<Map>()
              .map((d) => VibecodingDevice.fromJson(Map<String, dynamic>.from(d)))
              .toList();
        });
        break;
      case 'tasks.snapshot':
        setState(() {
          for (final item in (msg['tasks'] as List?) ?? []) {
            if (item is Map) {
              final t = VibecodingTask.fromJson(Map<String, dynamic>.from(item));
              _tasks[t.taskId] = t;
            }
          }
        });
        break;
      case 'task.event':
        _onTaskEvent(msg);
        break;
      case 'projects.response':
        setState(() {
          _projects = ((msg['projects'] as List?) ?? [])
              .whereType<Map>()
              .map((p) => VibecodingProject.fromJson(Map<String, dynamic>.from(p)))
              .toList();
          _tools = Map<String, bool>.from(msg['tools'] ?? {});
          if (_projects.isNotEmpty &&
              (_selectedProject == null ||
                  !_projects.any((p) => p.path == _selectedProject))) {
            _selectedProject = _projects.first.path;
          }
          final available = _tools.entries.where((e) => e.value).map((e) => e.key).toSet();
          if (!available.contains(_selectedTool) && available.isNotEmpty) {
            _selectedTool = available.first;
          }
        });
        break;
      case 'dispatch.error':
        final taskId = (msg['task_id'] ?? '').toString();
        final task = _tasks[taskId];
        if (task != null) {
          setState(() {
            task.status = VibeStatus.failed;
            task.error = (msg['reason'] ?? '派发失败').toString();
          });
        }
        break;
    }
  }

  void _onTaskEvent(Map<String, dynamic> msg) {
    final taskId = (msg['task_id'] ?? '').toString();
    if (taskId.isEmpty) return;
    final event = (msg['event'] ?? '').toString();
    final data = Map<String, dynamic>.from(msg['data'] ?? {});
    final task = _tasks[taskId];
    setState(() {
      if (task == null) {
        if (event != 'started') return;
        _tasks[taskId] = VibecodingTask(
          taskId: taskId,
          deviceId: msg['device_id']?.toString(),
          tool: data['tool']?.toString(),
          project: data['project']?.toString(),
          projectName: data['project_name']?.toString(),
          source: data['source']?.toString(),
          input: (data['input'] ?? '').toString(),
          status: VibeStatus.running,
          startedTs: (msg['ts'] as num?)?.toInt(),
        );
        return;
      }
      switch (event) {
        case 'started':
          task.status = VibeStatus.running;
          break;
        case 'milestone':
          if (data['stage'] == 'cancelled') task.status = VibeStatus.cancelled;
          break;
        case 'done':
          task.status = VibeStatus.done;
          task.output = (data['output'] ?? '').toString();
          task.durationMs = (data['duration_ms'] as num?)?.toInt();
          task.code = (data['code'] as num?)?.toInt();
          break;
        case 'failed':
          task.status = VibeStatus.failed;
          task.error = (data['error'] ?? '执行失败').toString();
          task.durationMs = (data['duration_ms'] as num?)?.toInt();
          break;
      }
    });
  }

  void _dispatch() {
    final project = _selectedProject;
    final input = _inputController.text.trim();
    if (project == null || input.isEmpty) return;
    final taskId = _service.newTaskId();
    final matching = _projects.where((p) => p.path == project).toList();
    final projName = matching.isNotEmpty ? matching.first.name : null;
    setState(() {
      _tasks[taskId] = VibecodingTask(
        taskId: taskId,
        tool: _selectedTool,
        project: project,
        projectName: projName,
        source: 'mobile',
        input: input,
        status: VibeStatus.pending,
        startedTs: DateTime.now().millisecondsSinceEpoch,
      );
    });
    _service.ensureConnected();
    _service.dispatchTask(taskId: taskId, tool: _selectedTool, project: project, input: input);
    _inputController.clear();
  }

  List<VibecodingTask> get _sortedTasks {
    final list = _tasks.values.toList();
    list.sort((a, b) => (b.startedTs ?? 0).compareTo(a.startedTs ?? 0));
    return list;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final online = _service.connected.value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('VibeCoding'),
        actions: [
          Chip(
            avatar: Icon(online ? Icons.link : Icons.link_off, size: 16, color: online ? Colors.green : scheme.outline),
            label: Text(online ? '已连接' : '离线', style: const TextStyle(fontSize: 12)),
            visualDensity: VisualDensity.compact,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await _loadRestTasks();
          _projectsRequested = false;
          await _service.ensureConnected();
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_devices.isNotEmpty) ..._buildDeviceCard(scheme),
            _buildDispatchCard(scheme),
            const SizedBox(height: 16),
            Text('最近任务', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: scheme.primary)),
            const SizedBox(height: 8),
            if (_sortedTasks.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 32),
                child: Center(child: Text('暂无任务，先在上方派发一个', style: TextStyle(color: scheme.outline))),
              )
            else
              ..._sortedTasks.map((t) => _taskTile(t, scheme)),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildDeviceCard(ColorScheme scheme) {
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: _devices
                .map((d) => Row(
                      children: [
                        const Icon(Icons.computer, size: 18, color: Colors.green),
                        const SizedBox(width: 8),
                        Expanded(child: Text(d.name, style: const TextStyle(fontSize: 13))),
                        Text(d.activeTask == null ? '空闲' : '执行中', style: TextStyle(fontSize: 12, color: d.activeTask == null ? scheme.outline : scheme.primary)),
                      ],
                    ))
                .toList(),
          ),
        ),
      ),
      const SizedBox(height: 12),
    ];
  }

  Widget _buildDispatchCard(ColorScheme scheme) {
    final availableTools = _tools.isEmpty
        ? const ['opencode', 'claude', 'codex']
        : _tools.entries.where((e) => e.value).map((e) => e.key).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.bolt, size: 18, color: scheme.primary),
                const SizedBox(width: 6),
                const Text('派发新任务', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 10),
            if (_projects.isEmpty)
              Text('未获取到项目列表（桌面插件未连接或未扫描项目）', style: TextStyle(fontSize: 12, color: scheme.outline))
            else
              DropdownButtonFormField<String>(
                value: _selectedProject,
                isDense: true,
                decoration: const InputDecoration(labelText: '项目', border: OutlineInputBorder(), isDense: true),
                items: _projects
                    .map((p) => DropdownMenuItem(value: p.path, child: Text(p.name, overflow: TextOverflow.ellipsis)))
                    .toList(),
                onChanged: (v) => setState(() => _selectedProject = v),
              ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              children: availableTools
                  .map((t) => ChoiceChip(
                        label: Text(t),
                        selected: _selectedTool == t,
                        onSelected: (_) => setState(() => _selectedTool = t),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _inputController,
              maxLines: 3,
              minLines: 2,
              decoration: const InputDecoration(
                hintText: '描述任务，例如：修复登录页的空指针异常并补上单测',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: (_selectedProject != null && _inputController.text.trim().isNotEmpty) ? _dispatch : null,
                icon: const Icon(Icons.send_rounded, size: 18),
                label: const Text('派发到桌面执行'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _taskTile(VibecodingTask t, ColorScheme scheme) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        dense: true,
        leading: _statusIcon(t.status),
        title: Text(
          '${t.tool ?? '?'} · ${t.projectName ?? t.project ?? '?'}',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          t.error ?? (t.input.isEmpty ? t.source ?? '' : t.input),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontSize: 12, color: scheme.outline),
        ),
        trailing: Text(
          t.isRunning ? '运行中' : _formatMeta(t),
          style: TextStyle(fontSize: 11, color: scheme.outline),
        ),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => VibecodingTaskScreen(task: t)),
        ),
      ),
    );
  }

  Widget _statusIcon(VibeStatus status) {
    switch (status) {
      case VibeStatus.running:
      case VibeStatus.pending:
        return const SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(strokeWidth: 2.5),
        );
      case VibeStatus.done:
        return const Icon(Icons.check_circle, color: Colors.green, size: 22);
      case VibeStatus.failed:
        return const Icon(Icons.error, color: Colors.red, size: 22);
      case VibeStatus.cancelled:
        return const Icon(Icons.cancel, color: Colors.orange, size: 22);
      default:
        return const Icon(Icons.help_outline, size: 22);
    }
  }

  String _formatMeta(VibecodingTask t) {
    if (t.durationMs != null) {
      final s = t.durationMs! / 1000;
      return s >= 60 ? '${(s / 60).toStringAsFixed(1)}min' : '${s.toStringAsFixed(1)}s';
    }
    final ts = t.startedTs;
    if (ts == null) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(ts);
    return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }
}
