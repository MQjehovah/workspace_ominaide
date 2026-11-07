import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/loading_state.dart';

/// Mobile view of the persistent Agent task API (backed by BotRun).
class AgentTasksScreen extends StatefulWidget {
  const AgentTasksScreen({super.key});

  @override
  State<AgentTasksScreen> createState() => _AgentTasksScreenState();
}

class _AgentTasksScreenState extends State<AgentTasksScreen> {
  List<Map<String, dynamic>> _tasks = [];
  bool _loading = true;
  bool _creating = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer =
        Timer.periodic(const Duration(seconds: 4), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final tasks = await ApiService().listAgentTasks();
      if (!mounted) return;
      setState(() {
        _tasks = tasks;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _create() async {
    final controller = TextEditingController();
    final goal = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('新建 Agent 任务'),
        content: TextField(
          controller: controller,
          autofocus: true,
          minLines: 3,
          maxLines: 8,
          decoration: const InputDecoration(
            hintText: '例如：准备明天客户会，汇总相关邮件和上次会议纪要',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('创建'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (goal == null || goal.isEmpty || !mounted) return;
    setState(() => _creating = true);
    try {
      await ApiService().createAgentTask(goal);
      if (!mounted) return;
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建失败: $e')),
      );
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _open(Map<String, dynamic> task) async {
    final id = (task['id'] as num?)?.toInt();
    if (id == null) return;
    final detail = await ApiService().getAgentTask(id);
    if (!mounted) return;
    final palette = AppPalette.of(context);
    final steps = (detail['steps'] as List? ?? const []);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (context) => SafeArea(
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.7,
          maxChildSize: 0.92,
          builder: (context, scrollController) => ListView(
            controller: scrollController,
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
            children: [
              Text(
                (detail['input'] ?? 'Agent 任务').toString(),
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  _statusChip(palette, (detail['status'] ?? '').toString()),
                  const SizedBox(width: 8),
                  Text(
                    (detail['created_at'] ?? '')
                        .toString()
                        .replaceFirst('T', ' '),
                    style: TextStyle(fontSize: 10, color: palette.muted),
                  ),
                ],
              ),
              if ((detail['error'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  detail['error'].toString(),
                  style: TextStyle(fontSize: 11, color: palette.accent),
                ),
              ],
              const SizedBox(height: 14),
              if (steps.isEmpty)
                Text(
                  '还没有执行步骤',
                  style: TextStyle(fontSize: 12, color: palette.muted),
                )
              else
                for (final raw in steps)
                  if (raw is Map)
                    _StepTile(
                      step: raw.map((k, v) => MapEntry(k.toString(), v)),
                      palette: palette,
                    ),
              if (!['done', 'failed', 'cancelled'].contains(detail['status']))
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await ApiService().cancelAgentTask(id);
                      if (context.mounted) Navigator.pop(context);
                      await _load();
                    },
                    icon: const Icon(Icons.stop_rounded, size: 17),
                    label: const Text('取消任务'),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statusChip(AppPalette palette, String status) {
    final label = switch (status) {
      'queued' => '排队中',
      'running' => '执行中',
      'waiting_approval' => '待审批',
      'done' => '已完成',
      'failed' => '失败',
      'cancelled' => '已取消',
      _ => status,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: status == 'failed'
            ? palette.accent.withValues(alpha: 0.12)
            : palette.primarySoft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 9,
          fontWeight: FontWeight.w800,
          color: status == 'failed' ? palette.accent : palette.primary,
        ),
      ),
    );
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
              kicker: 'Agent',
              title: 'AI 任务',
              subtitle: '多步执行、工具调用与审批',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建任务',
                  onTap: _creating ? null : _create,
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: _load,
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? const SkeletonList(count: 5)
                  : _tasks.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(height: 50),
                            EmptyState(
                              icon: Icons.auto_awesome_motion_rounded,
                              title: '还没有 Agent 任务',
                              subtitle: '创建一个目标，让助手规划并执行多步任务。',
                            ),
                          ],
                        )
                      : RefreshIndicator(
                          onRefresh: _load,
                          color: palette.primary,
                          child: ListView.builder(
                            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                            itemCount: _tasks.length,
                            itemBuilder: (context, index) {
                              final task = _tasks[index];
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 9),
                                child: AppCard(
                                  onTap: () => _open(task),
                                  child: Row(
                                    children: [
                                      Container(
                                        width: 34,
                                        height: 34,
                                        decoration: BoxDecoration(
                                          color: palette.primarySoft,
                                          borderRadius:
                                              BorderRadius.circular(10),
                                        ),
                                        child: Icon(
                                          Icons.auto_awesome_motion_rounded,
                                          size: 18,
                                          color: palette.primary,
                                        ),
                                      ),
                                      const SizedBox(width: 10),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              (task['input'] ?? 'Agent 任务')
                                                  .toString(),
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(
                                                fontSize: 12.5,
                                                fontWeight: FontWeight.w600,
                                                color: palette.ink,
                                              ),
                                            ),
                                            const SizedBox(height: 3),
                                            Text(
                                              (task['created_at'] ?? '')
                                                  .toString()
                                                  .replaceFirst('T', ' '),
                                              style: TextStyle(
                                                fontSize: 9.5,
                                                color: palette.muted,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(width: 6),
                                      _statusChip(
                                        palette,
                                        (task['status'] ?? '').toString(),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepTile extends StatelessWidget {
  const _StepTile({required this.step, required this.palette});

  final Map<String, dynamic> step;
  final AppPalette palette;

  @override
  Widget build(BuildContext context) {
    final type = (step['type'] ?? 'tool').toString();
    final status = (step['status'] ?? '').toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 7),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: palette.background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: palette.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '#${step['seq'] ?? ''}',
                style: TextStyle(fontSize: 9, color: palette.muted),
              ),
              const SizedBox(width: 6),
              Text(
                (step['tool_name'] ?? type).toString(),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: palette.ink,
                ),
              ),
              const Spacer(),
              Text(
                status,
                style: TextStyle(
                  fontSize: 9,
                  color: status == 'ok' ? palette.success : palette.accent,
                ),
              ),
            ],
          ),
          if ((step['result'] ?? '').toString().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              step['result'].toString(),
              maxLines: 6,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10.5,
                height: 1.5,
                color: palette.muted,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
