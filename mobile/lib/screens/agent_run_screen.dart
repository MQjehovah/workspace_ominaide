import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Live view of one BotRun: steps, token stream, approvals and controls.
class AgentRunScreen extends StatefulWidget {
  const AgentRunScreen({super.key, required this.runId, this.title});

  final int runId;
  final String? title;

  @override
  State<AgentRunScreen> createState() => _AgentRunScreenState();
}

class _AgentRunScreenState extends State<AgentRunScreen> {
  Map<String, dynamic> _detail = {};
  List<Map<String, dynamic>> _steps = [];
  String _output = '';
  String _status = 'queued';
  String? _error;
  Map<String, dynamic>? _approval;
  StreamSubscription<Map<String, dynamic>>? _sub;
  bool _loading = true;
  bool _deciding = false;

  @override
  void initState() {
    super.initState();
    _loadDetail().whenComplete(() {
      if (mounted) _startStream();
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _loadDetail() async {
    try {
      final detail = await ApiService().getAgentTaskDetail(widget.runId);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _steps = ((detail['steps'] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
            .toList();
        _status = (detail['status'] ?? 'queued').toString();
        _output = (detail['output'] ?? detail['partial'] ?? '').toString();
        _error = (detail['error'] ?? '').toString().isEmpty
            ? null
            : detail['error'].toString();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _startStream() {
    _sub?.cancel();
    _sub = ApiService().streamAgentRun(widget.runId).listen(
      _onEvent,
      onError: (Object e) {
        if (!mounted) return;
        // SSE can fail through a proxy; fall back to the persisted snapshot.
        _loadDetail();
      },
    );
  }

  void _onEvent(Map<String, dynamic> event) {
    if (!mounted) return;
    final type = (event['type'] ?? '').toString();
    switch (type) {
      case 'run_started':
        setState(() {
          _status = (event['status'] ?? _status).toString();
          _output = '';
        });
        break;
      case 'run_status':
        setState(() => _status = (event['status'] ?? _status).toString());
        break;
      case 'step':
        final id = event['step_id'];
        if (id == null) break;
        final step = <String, dynamic>{...event};
        final index = _steps.indexWhere((s) => s['step_id'] == id);
        setState(() {
          if (index >= 0) {
            _steps[index] = step;
          } else {
            _steps.add(step);
            _steps.sort((a, b) =>
                ((a['seq'] as num?)?.toInt() ?? 0)
                    .compareTo((b['seq'] as num?)?.toInt() ?? 0));
          }
          if (step['step_type'] == 'approval' &&
              step['status'] == 'pending' &&
              step['approval_id'] != null) {
            _approval = {
              'approval_id': step['approval_id'],
              'tool': step['tool'],
              'arguments': step['arguments'],
              'reason': step['content'],
            };
          }
        });
        break;
      case 'approval':
        setState(() => _approval = event);
        break;
      case 'token':
        final delta = (event['content'] ?? '').toString();
        if (delta.isNotEmpty) setState(() => _output += delta);
        break;
      case 'done':
        setState(() {
          _status = (event['status'] ?? _status).toString();
          final reply = (event['reply'] ?? '').toString();
          if (reply.isNotEmpty) _output = reply;
          final err = (event['error'] ?? '').toString();
          _error = err.isEmpty ? null : err;
          _approval = null;
        });
        _sub?.cancel();
        break;
      case 'error':
        setState(() {
          _error = (event['content'] ?? '运行出错').toString();
        });
        break;
    }
  }

  Future<void> _decide(bool approved, {bool remember = false}) async {
    final approvalId = (_approval?['approval_id'] as num?)?.toInt();
    if (approvalId == null) return;
    setState(() => _deciding = true);
    try {
      await ApiService().decideApproval(
        approvalId,
        approved: approved,
        remember: remember,
      );
      if (!mounted) return;
      setState(() => _approval = null);
      await _loadDetail();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('审批失败：${e.toString().replaceFirst('Exception: ', '')}')),
      );
    } finally {
      if (mounted) setState(() => _deciding = false);
    }
  }

  Future<void> _cancel() async {
    try {
      await ApiService().cancelAgentTask(widget.runId);
      await _loadDetail();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('取消失败：$e')),
      );
    }
  }

  bool get _active => !['done', 'failed', 'cancelled'].contains(_status);

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Run',
              title: '运行详情',
              subtitle: widget.title ?? 'Bot 任务',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: () async {
                    await _loadDetail();
                    if (mounted) _startStream();
                  },
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: () async {
                        await _loadDetail();
                        _startStream();
                      },
                      color: palette.primary,
                      child: ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                        children: [
                          _statusCard(palette),
                          if (_approval != null) ...[
                            const SizedBox(height: 10),
                            _approvalCard(palette),
                          ],
                          if (_error != null) ...[
                            const SizedBox(height: 10),
                            AppCard(
                              color: palette.accent.withValues(alpha: 0.08),
                              child: Text(
                                _error!,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: palette.accent,
                                ),
                              ),
                            ),
                          ],
                          const SizedBox(height: 10),
                          if (_steps.isEmpty)
                            AppCard(
                              child: Text(
                                _active ? '正在准备…' : '没有执行步骤',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: palette.muted,
                                ),
                              ),
                            )
                          else
                            for (final step in _steps) ...[
                              _StepCard(step: step),
                              const SizedBox(height: 8),
                            ],
                          if (_output.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            _outputCard(palette),
                          ],
                          if (_active) ...[
                            const SizedBox(height: 12),
                            OutlinedButton.icon(
                              onPressed: _cancel,
                              icon: const Icon(Icons.stop_rounded, size: 17),
                              label: const Text('取消任务'),
                            ),
                          ],
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusCard(AppPalette palette) {
    final tokensIn = _detail['tokens_in'] ?? 0;
    final tokensOut = _detail['tokens_out'] ?? 0;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _statusChip(palette),
              const Spacer(),
              Text(
                'tokens $tokensIn / $tokensOut',
                style: TextStyle(fontSize: 10, color: palette.muted),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            (_detail['input'] ?? widget.title ?? '').toString(),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12.5, height: 1.5, color: palette.ink),
          ),
        ],
      ),
    );
  }

  Widget _approvalCard(AppPalette palette) {
    final tool = (_approval?['tool'] ?? '工具').toString();
    final reason = (_approval?['reason'] ?? '').toString();
    final args = _approval?['arguments'];
    final argsText = args is Map ? const JsonEncoder.withIndent('  ').convert(args) : '';
    return AppCard(
      color: palette.accent.withValues(alpha: 0.08),
      borderColor: palette.accent.withValues(alpha: 0.35),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.lock_outline_rounded, size: 16, color: palette.accent),
              const SizedBox(width: 5),
              Text(
                '需要审批 · $tool',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: palette.accent,
                ),
              ),
            ],
          ),
          if (reason.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              reason,
              style: TextStyle(fontSize: 11.5, color: palette.ink),
            ),
          ],
          if (argsText.isNotEmpty) ...[
            const SizedBox(height: 6),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: palette.background,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                argsText.length > 800 ? '${argsText.substring(0, 800)}…' : argsText,
                maxLines: 10,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 10.5,
                  height: 1.5,
                  fontFamily: 'monospace',
                  color: palette.ink,
                ),
              ),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  onPressed: _deciding ? null : () => _decide(true),
                  child: const Text('允许一次'),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: OutlinedButton(
                  onPressed: _deciding ? null : () => _decide(true, remember: true),
                  child: const Text('总是允许'),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: OutlinedButton(
                  onPressed: _deciding ? null : () => _decide(false),
                  child: const Text('拒绝'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _outputCard(AppPalette palette) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '输出',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 0.6,
              fontWeight: FontWeight.w800,
              color: palette.muted,
            ),
          ),
          const SizedBox(height: 6),
          SelectableText(
            _output,
            style: TextStyle(fontSize: 12.5, height: 1.65, color: palette.ink),
          ),
        ],
      ),
    );
  }

  Widget _statusChip(AppPalette palette) {
    final label = switch (_status) {
      'queued' => '排队中',
      'running' => '执行中',
      'waiting_approval' => '待审批',
      'done' => '已完成',
      'failed' => '失败',
      'cancelled' => '已取消',
      _ => _status,
    };
    final color = _status == 'failed'
        ? palette.accent
        : _status == 'waiting_approval'
            ? palette.accent
            : _status == 'done'
                ? palette.success
                : palette.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 9.5,
          fontWeight: FontWeight.w800,
          color: color,
        ),
      ),
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({required this.step});

  final Map<String, dynamic> step;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final status = (step['status'] ?? '').toString();
    final type = (step['step_type'] ?? step['type'] ?? 'tool').toString();
    final tool = (step['tool'] ?? (type == 'approval' ? '审批' : '步骤')).toString();
    final content = (step['content'] ?? '').toString();
    final arguments = step['arguments'];
    final argsText =
        arguments is Map ? const JsonEncoder.withIndent('  ').convert(arguments) : '';
    final running = status == 'running';
    final isApproval = type == 'approval';
    final color = status == 'error' || status == 'denied'
        ? palette.accent
        : isApproval
            ? palette.accent
            : status == 'running'
                ? palette.primary
                : palette.success;

    return AppCard(
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(top: 4),
        shape: const Border(),
        collapsedShape: const Border(),
        leading: running
            ? SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              )
            : Icon(
                isApproval
                    ? Icons.lock_outline_rounded
                    : status == 'error' || status == 'denied'
                        ? Icons.error_outline_rounded
                        : Icons.check_circle_outline_rounded,
                size: 17,
                color: color,
              ),
        title: Text(
          tool,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: palette.ink,
          ),
        ),
        subtitle: Text(
          isApproval
              ? '审批 · $status'
              : status.isEmpty
                  ? type
                  : status,
          style: TextStyle(fontSize: 10, color: palette.muted),
        ),
        children: [
          if (argsText.isNotEmpty)
            _block(palette, '参数', argsText),
          if (content.isNotEmpty)
            _block(palette, '结果', content),
        ],
      ),
    );
  }

  Widget _block(AppPalette palette, String title, String text) {
    final clipped = text.length > 4000 ? '${text.substring(0, 4000)}…' : text;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: palette.background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(fontSize: 9.5, color: palette.muted),
          ),
          const SizedBox(height: 3),
          SelectableText(
            clipped,
            style: TextStyle(
              fontSize: 10.5,
              height: 1.5,
              fontFamily: 'monospace',
              color: palette.ink,
            ),
          ),
        ],
      ),
    );
  }
}
