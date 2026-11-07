import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Coding runs for a project: history, status and starting a new run.
class ProjectRunsScreen extends StatefulWidget {
  const ProjectRunsScreen({
    super.key,
    required this.projectId,
    required this.projectName,
  });

  final int projectId;
  final String projectName;

  @override
  State<ProjectRunsScreen> createState() => _ProjectRunsScreenState();
}

class _ProjectRunsScreenState extends State<ProjectRunsScreen> {
  List<Map<String, dynamic>> _runs = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final runs = await ApiService().listProjectRuns(widget.projectId);
      if (!mounted) return;
      setState(() {
        _runs = runs;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _startRun() async {
    final ctl = TextEditingController();
    final branch = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('新建运行'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: ctl,
              autofocus: true,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(
                labelText: '任务说明',
                hintText: '例如：修复登录页的校验问题，并补充测试',
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: branch,
              decoration: const InputDecoration(
                labelText: '分支（可选）',
                hintText: 'feature/login-fix',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('开始'),
          ),
        ],
      ),
    );
    final instruction = ctl.text.trim();
    final branchName = branch.text.trim();
    ctl.dispose();
    branch.dispose();
    if (!mounted || ok != true || instruction.isEmpty) return;
    try {
      await ApiService().startProjectRun(
        widget.projectId,
        instruction,
        branch: branchName.isEmpty ? null : branchName,
      );
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已提交运行')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('启动失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _showRun(Map<String, dynamic> run) async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  SourcePill(
                    label: (run['status'] ?? 'unknown').toString(),
                    color: _statusColor(palette, (run['status'] ?? '').toString()),
                  ),
                  const Spacer(),
                  Text(
                    _fmtTime(run['created_at']),
                    style: TextStyle(fontSize: 10.5, color: palette.muted),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text('任务', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: palette.muted)),
              const SizedBox(height: 4),
              Text(
                (run['input'] ?? '').toString(),
                style: TextStyle(fontSize: 12, height: 1.6, color: palette.ink),
              ),
              if ((run['output'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('输出', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: palette.muted)),
                const SizedBox(height: 4),
                Text(
                  run['output'].toString(),
                  style: TextStyle(fontSize: 12, height: 1.6, color: palette.ink),
                ),
              ],
              if ((run['error'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('错误', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: palette.accent)),
                const SizedBox(height: 4),
                Text(
                  run['error'].toString(),
                  style: TextStyle(fontSize: 12, height: 1.6, color: palette.accent),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Color _statusColor(AppPalette palette, String status) {
    if (status == 'success' || status == 'completed') return palette.success;
    if (status == 'failed' || status == 'error') return palette.accent;
    return palette.primary;
  }

  String _fmtTime(dynamic raw) {
    final d = DateTime.tryParse((raw ?? '').toString());
    if (d == null) return '';
    final local = d.toLocal();
    return '${local.month}/${local.day} '
        '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
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
              kicker: 'Coding',
              title: widget.projectName,
              subtitle: '项目运行记录',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建运行',
                  onTap: _startRun,
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : _error != null
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _load),
                          ],
                        )
                      : _runs.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.play_circle_outline,
                                  title: '还没有运行记录',
                                  subtitle: '点击右上角 + 提交一个 coding 任务。',
                                  action: FilledButton.icon(
                                    onPressed: _startRun,
                                    icon: const Icon(Icons.add, size: 17),
                                    label: const Text('新建运行'),
                                  ),
                                ),
                              ],
                            )
                          : RefreshIndicator(
                              onRefresh: _load,
                              color: palette.primary,
                              child: ListView.builder(
                                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                                itemCount: _runs.length,
                                itemBuilder: (context, index) {
                                  final run = _runs[index];
                                  final status = (run['status'] ?? '').toString();
                                  final branch = (run['branch'] ?? '').toString();
                                  final when = _fmtTime(run['created_at']);
                                  final subtitle = branch.isEmpty ? when : '$branch · $when';
                                  return Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: AppCard(
                                      onTap: () => _showRun(run),
                                      child: Row(
                                        children: [
                                          Container(
                                            width: 34,
                                            height: 34,
                                            decoration: BoxDecoration(
                                              color: palette.primarySoft,
                                              borderRadius: BorderRadius.circular(10),
                                            ),
                                            child: Icon(
                                              Icons.terminal_rounded,
                                              size: 17,
                                              color: _statusColor(palette, status),
                                            ),
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  (run['input'] ?? '运行').toString(),
                                                  maxLines: 1,
                                                  overflow: TextOverflow.ellipsis,
                                                  style: TextStyle(
                                                    fontSize: 12.5,
                                                    fontWeight: FontWeight.w700,
                                                    color: palette.ink,
                                                  ),
                                                ),
                                                const SizedBox(height: 2),
                                                Text(
                                                  subtitle,
                                                  style: TextStyle(
                                                    fontSize: 10,
                                                    color: palette.muted,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          SourcePill(
                                            label: status,
                                            color: _statusColor(palette, status),
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
