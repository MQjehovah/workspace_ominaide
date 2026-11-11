import 'dart:async';

import 'package:flutter/foundation.dart';

import 'host_channel_service.dart';

/// Vibecoding protocol client over the shared host channel
/// (`channel: "vibecoding"`). Transport lives in [HostChannelService].
class VibecodingService {
  final HostChannelService _host = HostChannelService();

  static final VibecodingService _instance = VibecodingService._();
  factory VibecodingService() => _instance;
  VibecodingService._();

  static const String channel = 'vibecoding';

  /// Broadcast stream of vibecoding messages (device.status / task.event /
  /// tasks.snapshot / projects.response / dispatch.error / pong).
  Stream<Map<String, dynamic>> get stream =>
      _host.stream.where((m) => m['channel'] == channel);

  ValueNotifier<bool> get connected => _host.connected;

  Future<void> ensureConnected() => _host.ensureConnected();

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

  void stop() => _host.stop();
}
