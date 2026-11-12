import 'dart:async';

import 'package:flutter/widgets.dart';

import '../models/opencode_models.dart';
import 'api_service.dart';
import 'live_activity_service.dart';
import 'local_reminder_service.dart';
import 'vibecoding_service.dart';

/// One coding session that is currently running on a desktop machine.
class OpenCodeRun {
  OpenCodeRun({
    required this.machineId,
    required this.sessionId,
    required this.title,
    required this.directory,
    required this.startedAt,
    this.machineName = '',
  });

  final String machineId;
  final String sessionId;
  String title;
  String directory;
  String machineName;
  final DateTime startedAt;
  DateTime lastEventAt = DateTime.now();
  DateTime? finishedAt;
  String status = 'running';
  bool connectionLost = false;
  bool awaitingPermission = false;
  String permissionId = '';
  String permissionAction = '';
  List<String> permissionResources = const [];
  String permissionMessage = '';
  bool awaitingForm = false;
  String formId = '';
  String formTitle = '';
  List<Map<String, dynamic>> formFields = const [];

  String get key => '$machineId|$sessionId';

  Duration get elapsed => (finishedAt ?? DateTime.now()).difference(startedAt);
}

String formatRunDuration(Duration duration) {
  final seconds = duration.inSeconds < 0 ? 0 : duration.inSeconds;
  final hours = seconds ~/ 3600;
  final minutes = (seconds % 3600) ~/ 60;
  final rest = seconds % 60;
  if (hours > 0) {
    return '$hours:${minutes.toString().padLeft(2, '0')}:'
        '${rest.toString().padLeft(2, '0')}';
  }
  return '$minutes:${rest.toString().padLeft(2, '0')}';
}

/// App-wide watcher for OpenCode runs.
///
/// The session screen used to own the only event subscription, so leaving it
/// (or the app going to the background) silently stopped updating "运行中".
/// This singleton listens for the whole app, reconciles against the backend
/// session index after reconnects, and reports completion once.
class OpenCodeRunMonitor with WidgetsBindingObserver {
  OpenCodeRunMonitor._();

  static final OpenCodeRunMonitor _instance = OpenCodeRunMonitor._();
  factory OpenCodeRunMonitor() => _instance;

  final ValueNotifier<List<OpenCodeRun>> runs =
      ValueNotifier<List<OpenCodeRun>>(const []);
  final ValueNotifier<OpenCodeRun?> justCompleted =
      ValueNotifier<OpenCodeRun?>(null);
  final ValueNotifier<bool> active = ValueNotifier<bool>(false);

  final LiveActivityService _liveActivity = LiveActivityService();
  final Map<String, OpenCodeRun> _byKey = <String, OpenCodeRun>{};
  final Map<String, DateTime> _completedAt = <String, DateTime>{};
  final Map<String, String> _titles = <String, String>{};
  final Map<String, String> _directories = <String, String>{};
  final Map<String, String> _machineNames = <String, String>{};

  StreamSubscription<Map<String, dynamic>>? _sub;
  Timer? _timer;
  Timer? _completedTimer;
  bool _started = false;
  bool _reconciling = false;
  bool _appActive = true;
  DateTime? _backgroundedAt;
  DateTime? _lastAttemptAt;
  DateTime? _lastPingAt;
  DateTime? _lastPongAt;

  /// Called when a run completes while the app is in the foreground.
  void Function(OpenCodeRun run)? onCompleted;

  /// Called when a run is blocked on a permission choice.
  void Function(OpenCodeRun run)? onPermission;

  /// Called when a run is blocked on an ask_user form.
  void Function(OpenCodeRun run)? onForm;

  bool get appActive => _appActive;

  void start() {
    if (_started) return;
    _started = true;
    active.value = true;
    WidgetsBinding.instance.addObserver(this);
    _sub = VibecodingService().stream.listen(_onMessage);
    VibecodingService().connected.addListener(_onConnectionChanged);
    VibecodingService().ensureConnected();
    _lastPongAt = DateTime.now();
    _lastPingAt = DateTime.now();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _tick());
    unawaited(reconcile());
  }

  void stop() {
    if (!_started) return;
    _started = false;
    active.value = false;
    if (_byKey.isNotEmpty) unawaited(_liveActivity.endAll());
    _timer?.cancel();
    _timer = null;
    _completedTimer?.cancel();
    _completedTimer = null;
    _sub?.cancel();
    _sub = null;
    VibecodingService().connected.removeListener(_onConnectionChanged);
    WidgetsBinding.instance.removeObserver(this);
    _byKey.clear();
    _completedAt.clear();
    _titles.clear();
    _directories.clear();
    _machineNames.clear();
    _lastPingAt = null;
    _lastPongAt = null;
    runs.value = const [];
    justCompleted.value = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _appActive = true;
        final since = _backgroundedAt;
        _backgroundedAt = null;
        if (since != null &&
            DateTime.now().difference(since) > const Duration(seconds: 8)) {
          // The socket may have been suspended without a close event. Force a
          // fresh connection, then reconcile anything missed while away.
          unawaited(VibecodingService().reconnect());
        } else {
          VibecodingService().ensureConnected();
        }
        unawaited(reconcile());
        break;
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        _appActive = false;
        _backgroundedAt = DateTime.now();
        break;
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
        break;
    }
  }

  void _tick() {
    if (!_started || !_appActive) return;
    _heartbeat();
    final now = DateTime.now();
    final interval = _byKey.isEmpty
        ? const Duration(seconds: 60)
        : const Duration(seconds: 15);
    final last = _lastAttemptAt;
    if (last != null && now.difference(last) < interval) return;
    unawaited(reconcile());
  }

  void _heartbeat() {
    if (!VibecodingService().connected.value) return;
    final now = DateTime.now();
    final lastPong = _lastPongAt;
    if (lastPong != null &&
        now.difference(lastPong) > const Duration(seconds: 40)) {
      // No pong for two heartbeat cycles: treat the socket as dead. The next
      // connection will reconcile the session index.
      _lastPongAt = now;
      _lastPingAt = now;
      unawaited(VibecodingService().reconnect());
      return;
    }
    final lastPing = _lastPingAt;
    if (lastPing == null ||
        now.difference(lastPing) >= const Duration(seconds: 20)) {
      _lastPingAt = now;
      VibecodingService().ping();
    }
  }

  void _onConnectionChanged() {
    if (!_started) return;
    final online = VibecodingService().connected.value;
    if (online) {
      _lastPongAt = DateTime.now();
      _lastPingAt = DateTime.now();
    }
    if (_byKey.isNotEmpty) {
      for (final run in _byKey.values) {
        run.connectionLost = !online;
      }
      _publish();
    }
    if (online) unawaited(reconcile());
  }

  void _onMessage(Map<String, dynamic> msg) {
    if (!_started) return;
    final type = (msg['type'] ?? '').toString();
    if (type == 'pong') {
      _lastPongAt = DateTime.now();
      return;
    }
    if (type != 'oc.event') return;
    final sessionId = (msg['session_id'] ?? '').toString();
    final machineId = (msg['machine_id'] ?? '').toString();
    if (sessionId.isEmpty) return;
    final event = (msg['event'] ?? '').toString();
    final data = msg['data'] is Map
        ? Map<String, dynamic>.from(msg['data'] as Map)
        : const <String, dynamic>{};
    // Only lightweight lifecycle/permission events are needed app-wide. Text
    // deltas and tool calls go only to the open session screen.
    switch (event) {
      case 'session.execution.started':
      case 'session.text.started':
        _markRunning(machineId, sessionId);
        break;
      case 'session.execution.succeeded':
        _finish(machineId, sessionId, 'completed');
        break;
      case 'session.execution.failed':
        _finish(machineId, sessionId, 'failed');
        break;
      case 'session.execution.interrupted':
        _finish(machineId, sessionId, 'interrupted');
        break;
      case 'permission.asked':
        _permissionAsked(machineId, sessionId, data);
        break;
      case 'permission.replied':
        clearPermission(machineId, sessionId);
        break;
      case 'form.created':
        _formAsked(machineId, sessionId, data);
        break;
      case 'form.replied':
      case 'form.cancelled':
        clearForm(machineId, sessionId);
        break;
      default:
        break;
    }
  }

  void _permissionAsked(
    String machineId,
    String sessionId,
    Map<String, dynamic> data,
  ) {
    _markRunning(machineId, sessionId);
    final run = _byKey[_key(machineId, sessionId)];
    if (run == null) return;
    run.awaitingPermission = true;
    run.permissionId = (data['request_id'] ?? data['id'] ?? '').toString();
    run.permissionAction =
        (data['action'] ?? data['title'] ?? '需要确认').toString();
    run.permissionMessage = (data['message'] ?? '').toString();
    run.permissionResources = ((data['resources'] as List?) ?? const [])
        .map((value) => value.toString())
        .where((value) => value.isNotEmpty)
        .toList();
    _publish();
    if (_appActive) {
      onPermission?.call(run);
    } else {
      unawaited(
        LocalReminderService().showNow(
          title: 'OpenCode 需要确认',
          body: '${run.title} · ${run.permissionAction}',
        ),
      );
    }
  }

  void clearPermission(String? machineId, String sessionId) {
    final run = _byKey[_key(machineId ?? '', sessionId)];
    if (run == null || !run.awaitingPermission) return;
    run.awaitingPermission = false;
    run.permissionId = '';
    run.permissionAction = '';
    run.permissionMessage = '';
    run.permissionResources = const [];
    _publish();
  }

  void _formAsked(
    String machineId,
    String sessionId,
    Map<String, dynamic> data,
  ) {
    _markRunning(machineId, sessionId);
    final run = _byKey[_key(machineId, sessionId)];
    if (run == null) return;
    final raw = data['form'] is Map
        ? Map<String, dynamic>.from(data['form'] as Map)
        : data;
    final fields = (raw['fields'] as List?) ?? const [];
    run.awaitingForm = true;
    run.formId = (raw['form_id'] ?? raw['id'] ?? '').toString();
    run.formTitle = (raw['title'] ?? '需要你的选择').toString();
    run.formFields = fields
        .whereType<Map>()
        .map((field) => Map<String, dynamic>.from(field))
        .toList();
    _publish();
    if (_appActive) {
      onForm?.call(run);
    } else {
      unawaited(
        LocalReminderService().showNow(
          title: 'OpenCode 需要你选择',
          body: '${run.title} · ${run.formTitle}',
        ),
      );
    }
  }

  void clearForm(String? machineId, String sessionId) {
    final run = _byKey[_key(machineId ?? '', sessionId)];
    if (run == null || !run.awaitingForm) return;
    run.awaitingForm = false;
    run.formId = '';
    run.formTitle = '';
    run.formFields = const [];
    _publish();
  }

  String _key(String machineId, String sessionId) => '$machineId|$sessionId';

  /// Remember a session so completion notifications can use its real title,
  /// and add it to the run list when it is already busy.
  void trackSession(
    OpenCodeSession session,
    String? machineId, {
    bool running = false,
  }) {
    if (!_started || session.id.isEmpty) return;
    final mid = machineId ?? '';
    final key = _key(mid, session.id);
    _titles[key] = session.title;
    if (session.directory.isNotEmpty) _directories[key] = session.directory;
    final existing = _byKey[key];
    if (existing != null) {
      existing.title = session.title;
      if (session.directory.isNotEmpty) existing.directory = session.directory;
      if (running) existing.lastEventAt = DateTime.now();
      return;
    }
    if (running) {
      _markRunning(
        mid,
        session.id,
        title: session.title,
        directory: session.directory,
      );
    }
  }

  void trackSessions(List<OpenCodeSession> sessions, String? machineId) {
    for (final session in sessions) {
      trackSession(session, machineId, running: session.busy);
    }
  }

  void markPromptSent(OpenCodeSession session, String? machineId) {
    trackSession(session, machineId, running: true);
  }

  void markStopped(String? machineId, String sessionId) {
    final run = _byKey.remove(_key(machineId ?? '', sessionId));
    if (run == null) return;
    run.finishedAt = DateTime.now();
    run.status = 'interrupted';
    _completedAt[run.key] = run.finishedAt!;
    _publish();
    if (_byKey.isEmpty) {
      unawaited(
        _liveActivity.end(
          title: run.title,
          count: 1,
          startedAt: run.startedAt,
          status: 'interrupted',
          duration: formatRunDuration(run.elapsed),
        ),
      );
    }
  }

  bool isRunning(String? machineId, String sessionId) =>
      _byKey.containsKey(_key(machineId ?? '', sessionId));

  bool wasTracked(String? machineId, String sessionId) {
    final key = _key(machineId ?? '', sessionId);
    return _byKey.containsKey(key) ||
        _titles.containsKey(key) ||
        _completedAt.containsKey(key);
  }

  void _markRunning(
    String machineId,
    String sessionId, {
    String? title,
    String? directory,
  }) {
    if (sessionId.isEmpty) return;
    final key = _key(machineId, sessionId);
    _completedAt.remove(key);
    final existing = _byKey[key];
    if (existing != null) {
      existing.lastEventAt = DateTime.now();
      existing.status = 'running';
      existing.finishedAt = null;
      existing.connectionLost = !VibecodingService().connected.value;
      if (title != null && title.isNotEmpty) existing.title = title;
      if (directory != null && directory.isNotEmpty) {
        existing.directory = directory;
      }
      _publish();
      return;
    }
    _byKey[key] = OpenCodeRun(
      machineId: machineId,
      sessionId: sessionId,
      title: title?.isNotEmpty == true
          ? title!
          : (_titles[key]?.isNotEmpty == true ? _titles[key]! : 'OpenCode 会话'),
      directory: directory?.isNotEmpty == true
          ? directory!
          : (_directories[key] ?? ''),
      machineName: _machineNames[key] ?? '',
      startedAt: DateTime.now(),
    )..connectionLost = !VibecodingService().connected.value;
    _publish();
    if (_appActive) {
      // Ask once, at task start, instead of interrupting a background
      // completion with a permission prompt.
      unawaited(LocalReminderService().ensurePermission());
    }
  }

  void _finish(String machineId, String sessionId, String status) {
    final key = _key(machineId, sessionId);
    final run = _byKey.remove(key);
    if (run == null) return;
    run.finishedAt = DateTime.now();
    run.status = status;
    _completedAt[key] = run.finishedAt!;
    _publish();
    if (_byKey.isEmpty) {
      unawaited(
        _liveActivity.end(
          title: run.title,
          count: 1,
          startedAt: run.startedAt,
          status: status,
          duration: formatRunDuration(run.elapsed),
        ),
      );
    }
    if (status == 'interrupted') return;

    _completedTimer?.cancel();
    justCompleted.value = run;
    _completedTimer = Timer(const Duration(seconds: 15), () {
      if (justCompleted.value == run) justCompleted.value = null;
    });

    if (_appActive) {
      onCompleted?.call(run);
    } else {
      unawaited(
        LocalReminderService().showNow(
          title: status == 'failed' ? '编程任务失败' : '编程任务完成',
          body: '${run.title} · 用时 ${formatRunDuration(run.elapsed)}',
        ),
      );
    }
  }

  /// Pull the backend session index and reconcile it with live events. This is
  /// the safety net for missed websocket events and background suspensions.
  Future<void> reconcile() async {
    if (!_started || !ApiService().isLoggedIn || _reconciling) return;
    _reconciling = true;
    _lastAttemptAt = DateTime.now();
    try {
      final data = await ApiService().listCodingSessions();
      if (data == null) return;
      final rows = (data['sessions'] as List?) ?? const [];
      final now = DateTime.now();
      final runningKeys = <String>{};

      for (final raw in rows.whereType<Map>()) {
        final row = Map<String, dynamic>.from(raw);
        final sessionId = (row['session_id'] ?? row['id'] ?? '').toString();
        final machineId = (row['machine_id'] ?? '').toString();
        final agent = (row['agent'] ?? 'opencode').toString();
        if (sessionId.isEmpty || machineId.isEmpty) continue;
        // This monitor/live view is for native OpenCode sessions. Codex/Claude
        // CLI sessions are still visible on the desktop page.
        if (agent.isNotEmpty && agent != 'opencode') continue;
        final key = _key(machineId, sessionId);
        final title = (row['title'] ?? '').toString();
        final directory = (row['project'] ?? '').toString();
        final machineName = (row['machine_name'] ?? '').toString();
        if (title.isNotEmpty) _titles[key] = title;
        if (directory.isNotEmpty) _directories[key] = directory;
        if (machineName.isNotEmpty) _machineNames[key] = machineName;
        if (row['running'] != true) continue;
        runningKeys.add(key);

        final completed = _completedAt[key];
        if (completed != null &&
            now.difference(completed) < const Duration(seconds: 45)) {
          continue;
        }
        final existing = _byKey[key];
        if (existing != null) {
          existing.title = title.isNotEmpty ? title : existing.title;
          existing.directory =
              directory.isNotEmpty ? directory : existing.directory;
          existing.machineName =
              machineName.isNotEmpty ? machineName : existing.machineName;
          existing.lastEventAt = now;
          continue;
        }
        final updated = (row['updated'] as num?)?.toInt() ?? 0;
        final startedAt =
            updated > 0 ? DateTime.fromMillisecondsSinceEpoch(updated) : now;
        _byKey[key] = OpenCodeRun(
          machineId: machineId,
          sessionId: sessionId,
          title: title.isNotEmpty ? title : 'OpenCode 会话',
          directory: directory,
          machineName: machineName,
          startedAt: startedAt.isAfter(now) ? now : startedAt,
        );
      }

      for (final run in _byKey.values.toList()) {
        if (runningKeys.contains(run.key)) continue;
        // Snapshots are pushed every 15s. Do not complete a run that just
        // started until the index has had a chance to catch up.
        if (now.difference(run.lastEventAt) < const Duration(seconds: 20)) {
          continue;
        }
        _finish(run.machineId, run.sessionId, 'completed');
      }

      _publish();
      _completedAt.removeWhere(
        (_, at) => now.difference(at) > const Duration(minutes: 3),
      );
    } catch (_) {
      // Offline: keep the last known state and retry on the next tick.
    } finally {
      _reconciling = false;
    }
  }

  void _publish() {
    final list = _byKey.values.toList()
      ..sort((a, b) => b.startedAt.compareTo(a.startedAt));
    runs.value = List<OpenCodeRun>.unmodifiable(list);
    if (_byKey.isNotEmpty) _syncLiveActivity();
  }

  void _syncLiveActivity() {
    final list = _byKey.values.toList();
    if (list.isEmpty) return;
    final forms = list.where((run) => run.awaitingForm).toList();
    final permissions = list.where((run) => run.awaitingPermission).toList();
    final waiting = forms.isNotEmpty ? forms : permissions;
    final primary = waiting.isNotEmpty
        ? waiting.first
        : list.reduce((a, b) => a.lastEventAt.isAfter(b.lastEventAt) ? a : b);
    final earliest = list
        .map((run) => run.startedAt)
        .reduce((a, b) => a.isBefore(b) ? a : b);
    unawaited(
      _liveActivity.sync(
        title: primary.title,
        count: list.length,
        startedAt: earliest,
        status: waiting.isNotEmpty ? 'waiting' : 'running',
        action: forms.isNotEmpty
            ? '等待选择：${primary.formTitle}'
            : permissions.isNotEmpty
                ? '等待确认：${primary.permissionAction}'
                : '',
      ),
    );
  }
}
