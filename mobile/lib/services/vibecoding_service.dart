import 'dart:async';

import 'package:flutter/foundation.dart';

import 'host_channel_service.dart';

/// Vibecoding protocol client over the shared host channel
/// (`channel: "vibecoding"`). Transport lives in [HostChannelService].
class VibecodingService {
  final HostChannelService _host = HostChannelService();

  static final VibecodingService _instance = VibecodingService._();
  factory VibecodingService() => _instance;
  VibecodingService._() {
    _host.connected.addListener(_onConnected);
  }

  static const String channel = 'vibecoding';

  /// Sessions whose message detail this client is currently displaying.
  final Set<String> _watchedSessions = <String>{};

  void _onConnected() {
    if (!_host.connected.value) return;
    _sendPrefs();
    for (final sessionId in _watchedSessions) {
      _send({
        'type': 'session.watch',
        'session_id': sessionId,
        'watching': true,
      });
    }
  }

  void _sendPrefs() {
    _send({'type': 'viewer.prefs', 'detail_events': 'watched'});
  }

  /// Keep the websocket connected but only receive text/tool deltas for the
  /// session that is actually open on screen.
  void watchSession(String sessionId) {
    if (sessionId.isEmpty) return;
    if (_watchedSessions.add(sessionId)) {
      _send({
        'type': 'session.watch',
        'session_id': sessionId,
        'watching': true,
      });
    }
  }

  void unwatchSession(String sessionId) {
    if (sessionId.isEmpty) return;
    if (_watchedSessions.remove(sessionId)) {
      _send({
        'type': 'session.watch',
        'session_id': sessionId,
        'watching': false,
      });
    }
  }

  /// Broadcast stream of vibecoding messages (device.status / task.event /
  /// tasks.snapshot / projects.response / dispatch.error / pong).
  Stream<Map<String, dynamic>> get stream =>
      _host.stream.where((m) => m['channel'] == channel);

  ValueNotifier<bool> get connected => _host.connected;

  Future<void> ensureConnected() async {
    await _host.ensureConnected();
    if (_host.connected.value) _sendPrefs();
  }

  void _send(Map<String, dynamic> msg) => _host.send(channel, msg);

  String newTaskId() =>
      't-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-${DateTime.now().microsecondsSinceEpoch % 100000}';

  void dispatchTask({
    required String taskId,
    required String tool,
    required String project,
    required String input,
    String? machineId,
  }) {
    _send({
      'type': 'task.dispatch',
      'task_id': taskId,
      'tool': tool,
      'project': project,
      'input': input,
      if (machineId != null && machineId.isNotEmpty) 'machine_id': machineId,
    });
  }

  void cancelTask(String taskId) =>
      _send({'type': 'task.control', 'task_id': taskId, 'action': 'cancel'});

  void requestProjects({required String requestId, String? machineId}) =>
      _send({
        'type': 'projects.request',
        'request_id': requestId,
        if (machineId != null && machineId.isNotEmpty) 'machine_id': machineId,
      });

  String newRequestId() =>
      'r-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-${DateTime.now().microsecondsSinceEpoch % 10000}';

  void _request(
    String action, {
    required String requestId,
    required Map<String, dynamic> payload,
    String? machineId,
  }) {
    _send({
      'type': 'oc.request',
      'request_id': requestId,
      'action': action,
      'payload': payload,
      if (machineId != null && machineId.isNotEmpty) 'machine_id': machineId,
    });
  }

  /// List OpenCode sessions on the selected desktop machine.
  void requestSessions({
    required String requestId,
    String? machineId,
    int limit = 100,
  }) {
    _request(
      'sessions.list',
      requestId: requestId,
      machineId: machineId,
      payload: {'limit': limit},
    );
  }

  /// Fetch a page of messages. `cursor` loads the previous (older) page.
  void requestHistory({
    required String requestId,
    required String sessionId,
    String? machineId,
    int limit = 60,
    String? cursor,
  }) {
    _request(
      'session.history',
      requestId: requestId,
      machineId: machineId,
      payload: {
        'session_id': sessionId,
        'limit': limit,
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      },
    );
  }

  /// Create a new OpenCode session in the given project directory.
  void createSession({
    required String requestId,
    required String directory,
    String? title,
    String? machineId,
  }) {
    _request(
      'session.create',
      requestId: requestId,
      machineId: machineId,
      payload: {
        'directory': directory,
        if (title != null && title.isNotEmpty) 'title': title,
      },
    );
  }

  /// Delete a remote session.
  void deleteSession({
    required String requestId,
    required String sessionId,
    String? machineId,
  }) {
    _request(
      'session.delete',
      requestId: requestId,
      machineId: machineId,
      payload: {'session_id': sessionId},
    );
  }

  /// Continue an existing OpenCode session with new input.
  void sendPrompt({
    required String requestId,
    required String sessionId,
    required String text,
    String? machineId,
  }) {
    _request(
      'session.prompt',
      requestId: requestId,
      machineId: machineId,
      payload: {'session_id': sessionId, 'text': text},
    );
  }

  /// Answer an OpenCode `ask_user` form with the selected values.
  void replyForm({
    required String requestId,
    required String sessionId,
    required String formId,
    required Map<String, dynamic> answer,
    String? machineId,
  }) {
    _request(
      'session.form.reply',
      requestId: requestId,
      machineId: machineId,
      payload: {
        'session_id': sessionId,
        'form_id': formId,
        'answer': answer,
      },
    );
  }

  /// Answer an OpenCode permission prompt. [decision] is `once`, `always` or
  /// `reject`.
  void replyPermission({
    required String requestId,
    required String sessionId,
    required String permissionId,
    required String decision,
    String? machineId,
  }) {
    _request(
      'session.permission.reply',
      requestId: requestId,
      machineId: machineId,
      payload: {
        'session_id': sessionId,
        'permission_id': permissionId,
        'decision': decision,
      },
    );
  }

  void interruptSession({
    required String requestId,
    required String sessionId,
    String? machineId,
  }) {
    _request(
      'session.interrupt',
      requestId: requestId,
      machineId: machineId,
      payload: {'session_id': sessionId},
    );
  }

  void requestOpenCodeStatus({
    required String requestId,
    String? machineId,
  }) {
    _request(
      'server.status',
      requestId: requestId,
      machineId: machineId,
      payload: const {},
    );
  }

  /// Heartbeat used to notice half-open sockets that never delivered a close
  /// event (common after mobile network switches / background suspensions).
  void ping() => _send({'type': 'ping'});

  Future<void> reconnect() => _host.reconnect();

  void stop() => _host.stop();
}
