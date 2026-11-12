import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/opencode_models.dart';
import '../screens/opencode_session_screen.dart';
import '../screens/quick_capture_screen.dart';
import '../services/opencode_run_monitor.dart';
import '../services/vibecoding_service.dart';
import '../theme/app_theme.dart';

const _bubblePrefKey = 'global.run.bubble.bottom';

/// Floating entry available above every route.
///
/// Idle it opens 随手记; while a coding session is running it becomes a live
/// status pill. Completion temporarily turns it green so the result is visible
/// even if the user left the session screen.
class GlobalRunBubble extends StatefulWidget {
  const GlobalRunBubble({
    super.key,
    required this.navigatorKey,
    required this.popups,
  });

  final GlobalKey<NavigatorState> navigatorKey;
  final ValueListenable<int> popups;

  @override
  State<GlobalRunBubble> createState() => _GlobalRunBubbleState();
}

class _GlobalRunBubbleState extends State<GlobalRunBubble> {
  final OpenCodeRunMonitor _monitor = OpenCodeRunMonitor();
  final VibecodingService _service = VibecodingService();

  double _bottom = 150;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((prefs) {
      final value = prefs.getDouble(_bubblePrefKey);
      if (value != null && mounted) setState(() => _bottom = value);
    });
  }

  void _saveBottom() {
    SharedPreferences.getInstance()
        .then((prefs) => prefs.setDouble(_bubblePrefKey, _bottom));
  }

  void _openQuickCapture() {
    widget.navigatorKey.currentState?.push(
      MaterialPageRoute(builder: (_) => const QuickCaptureScreen()),
    );
  }

  void _openRunSheet() {
    final context = widget.navigatorKey.currentContext;
    if (context == null) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (_) => _RunSheet(navigatorKey: widget.navigatorKey),
    );
  }

  void _onTap(List<OpenCodeRun> runs, OpenCodeRun? completed) {
    if (runs.isEmpty && completed == null) {
      _openQuickCapture();
      return;
    }
    _openRunSheet();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([
        _monitor.active,
        _monitor.runs,
        _monitor.justCompleted,
        _service.connected,
        widget.popups,
      ]),
      builder: (context, _) {
        if (!_monitor.active.value ||
            widget.popups.value > 0 ||
            MediaQuery.of(context).viewInsets.bottom > 0) {
          return const SizedBox.shrink();
        }
        final palette = AppPalette.of(context);
        final runs = _monitor.runs.value;
        final completed = _monitor.justCompleted.value;
        final showCompleted = completed != null && runs.isEmpty;
        final online = _service.connected.value;
        final waitingForms = runs.where((run) => run.awaitingForm).length;
        final waitingPermissions =
            runs.where((run) => run.awaitingPermission).length;

        late final Color background;
        late final Color foreground;
        late final IconData icon;
        late final String label;

        if (runs.isNotEmpty) {
          if (waitingForms > 0) {
            background = const Color(0xFFF59E0B);
            foreground = Colors.white;
            icon = Icons.help_outline_rounded;
            label = '$waitingForms 待选择';
          } else if (waitingPermissions > 0) {
            background = const Color(0xFFF59E0B);
            foreground = Colors.white;
            icon = Icons.help_outline_rounded;
            label = '$waitingPermissions 待确认';
          } else if (!online) {
            background = const Color(0xFFF59E0B);
            foreground = Colors.white;
            icon = Icons.wifi_off_rounded;
            label = '${runs.length} 运行 · 离线';
          } else {
            background = palette.primary;
            foreground = Colors.white;
            icon = Icons.bolt_rounded;
            label = '${runs.length} 运行中';
          }
        } else if (showCompleted) {
          final failed = completed.status == 'failed';
          background = failed ? palette.accent : palette.success;
          foreground = Colors.white;
          icon = failed
              ? Icons.error_outline_rounded
              : Icons.check_circle_outline_rounded;
          label = failed ? '任务失败' : '任务完成';
        } else {
          background = palette.card;
          foreground = palette.primary;
          icon = Icons.edit_note_rounded;
          label = '随手记';
        }

        final maxBottom = MediaQuery.of(context).size.height -
            MediaQuery.of(context).padding.top -
            72;
        final bottom = _bottom.clamp(72.0, maxBottom < 72 ? 72.0 : maxBottom);

        return Positioned(
          right: 14,
          bottom: bottom,
          child: GestureDetector(
            onPanUpdate: (details) {
              setState(() {
                _bottom = (_bottom - details.delta.dy)
                    .clamp(72.0, maxBottom < 72 ? 72.0 : maxBottom);
              });
            },
            onPanEnd: (_) => _saveBottom(),
            onLongPress: _openRunSheet,
            child: Material(
              color: background,
              elevation: 7,
              shadowColor: background.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(24),
              child: InkWell(
                borderRadius: BorderRadius.circular(24),
                onTap: () => _onTap(runs, completed),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: completed != null || runs.isNotEmpty
                          ? Colors.transparent
                          : palette.line,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (runs.isNotEmpty &&
                          online &&
                          waitingForms == 0 &&
                          waitingPermissions == 0)
                        SizedBox(
                          width: 15,
                          height: 15,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: foreground,
                          ),
                        )
                      else
                        Icon(icon, size: 18, color: foreground),
                      const SizedBox(width: 6),
                      Text(
                        label,
                        style: TextStyle(
                          color: foreground,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _RunSheet extends StatefulWidget {
  const _RunSheet({required this.navigatorKey});

  final GlobalKey<NavigatorState> navigatorKey;

  @override
  State<_RunSheet> createState() => _RunSheetState();
}

class _RunSheetState extends State<_RunSheet> {
  final OpenCodeRunMonitor _monitor = OpenCodeRunMonitor();
  final VibecodingService _service = VibecodingService();
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  void _openRun(OpenCodeRun run) {
    Navigator.of(context).pop();
    widget.navigatorKey.currentState?.push(
      MaterialPageRoute(
        builder: (_) => OpenCodeSessionScreen(
          machineId: run.machineId,
          session: OpenCodeSession(
            id: run.sessionId,
            title: run.title,
            directory: run.directory,
            busy: true,
          ),
        ),
      ),
    );
  }

  void _quickCapture() {
    Navigator.of(context).pop();
    widget.navigatorKey.currentState?.push(
      MaterialPageRoute(builder: (_) => const QuickCaptureScreen()),
    );
  }

  void _stopRun(OpenCodeRun run) {
    _service.interruptSession(
      requestId: _service.newRequestId(),
      sessionId: run.sessionId,
      machineId: run.machineId,
    );
    _monitor.markStopped(run.machineId, run.sessionId);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('正在停止「${run.title}」')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return AnimatedBuilder(
      animation: Listenable.merge([
        _monitor.runs,
        _monitor.justCompleted,
        _service.connected,
      ]),
      builder: (context, _) {
        final runs = _monitor.runs.value;
        final completed = _monitor.justCompleted.value;
        final online = _service.connected.value;
        final waiting = runs.where(
          (run) => run.awaitingForm || run.awaitingPermission,
        );
        final stillRunning =
            completed != null && runs.any((run) => run.key == completed.key);

        return SafeArea(
          top: false,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.72,
            ),
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '运行中的任务',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: palette.ink,
                          ),
                        ),
                      ),
                      Chip(
                        avatar: Icon(
                          online ? Icons.link_rounded : Icons.link_off_rounded,
                          size: 14,
                          color: online ? palette.success : palette.accent,
                        ),
                        label: Text(
                          online ? '实时同步' : '离线 · 自动同步',
                          style: const TextStyle(fontSize: 10.5),
                        ),
                        visualDensity: VisualDensity.compact,
                        side: BorderSide(color: palette.line),
                        backgroundColor: palette.background,
                      ),
                    ],
                  ),
                  if (waiting.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFFBEB),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFFDE68A)),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.help_outline_rounded,
                            size: 15,
                            color: Color(0xFFB45309),
                          ),
                          const SizedBox(width: 7),
                          Expanded(
                            child: Text(
                              '有任务在等待你的选择，点开任务完成选择后会自动继续。',
                              style: TextStyle(
                                fontSize: 11,
                                height: 1.45,
                                color: const Color(0xFF92400E),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  if (!online && runs.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFFBEB),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFFDE68A)),
                      ),
                      child: const Text(
                        '实时连接已断开，正在重连。桌面端任务可能仍在运行，'
                        '这里会定时同步，完成后通知你。',
                        style: TextStyle(
                          fontSize: 11,
                          height: 1.5,
                          color: Color(0xFF92400E),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  if (runs.isEmpty && !stillRunning)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 20,
                      ),
                      decoration: BoxDecoration(
                        color: palette.background,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: palette.line),
                      ),
                      child: Column(
                        children: [
                          Icon(
                            Icons.task_alt_rounded,
                            size: 24,
                            color: palette.muted,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '当前没有运行中的任务',
                            style: TextStyle(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: palette.ink,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '从桌面端或手机发起的 OpenCode 任务会出现在这里。',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 10.5,
                              color: palette.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  for (final run in runs)
                    _RunTile(
                      run: run,
                      onOpen: () => _openRun(run),
                      onStop: () => _stopRun(run),
                    ),
                  if (completed != null && !stillRunning)
                    Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: completed.status == 'failed'
                            ? palette.accent.withValues(alpha: 0.08)
                            : palette.success.withValues(alpha: 0.09),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            completed.status == 'failed'
                                ? Icons.error_outline_rounded
                                : Icons.check_circle_outline_rounded,
                            size: 18,
                            color: completed.status == 'failed'
                                ? palette.accent
                                : palette.success,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '${completed.title} · '
                              '${completed.status == 'failed' ? '执行失败' : '已完成'}'
                              ' · ${formatRunDuration(completed.elapsed)}',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 11.5,
                                color: palette.ink,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _quickCapture,
                    icon: const Icon(Icons.edit_note_rounded, size: 19),
                    label: const Text('随手记'),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _RunTile extends StatelessWidget {
  const _RunTile({
    required this.run,
    required this.onOpen,
    required this.onStop,
  });

  final OpenCodeRun run;
  final VoidCallback onOpen;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final meta = [
      if (run.machineName.isNotEmpty) run.machineName,
      if (run.directory.isNotEmpty) run.directory.split(RegExp(r'[\\/]')).last,
      formatRunDuration(run.elapsed),
    ].join(' · ');
    return Material(
      color: palette.card,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onOpen,
        child: Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.fromLTRB(12, 10, 6, 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: palette.line),
          ),
          child: Row(
            children: [
              if (run.awaitingForm || run.awaitingPermission)
                Icon(
                  Icons.help_outline_rounded,
                  size: 19,
                  color: const Color(0xFFF59E0B),
                )
              else
                SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: palette.primary,
                  ),
                ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      run.title,
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
                      run.connectionLost ? '$meta · 连接中断' : meta,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10.5,
                        color:
                            run.connectionLost ? palette.accent : palette.muted,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: '停止',
                onPressed: onStop,
                icon: Icon(
                  Icons.stop_circle_outlined,
                  size: 20,
                  color: palette.accent,
                ),
              ),
              Icon(
                Icons.chevron_right_rounded,
                size: 18,
                color: palette.muted,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
