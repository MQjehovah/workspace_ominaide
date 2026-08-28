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
    String? deviceId,
  }) {
    _send({
      'type': 'task.dispatch',
      'task_id': taskId,
      'tool': tool,
      'project': project,
      'input': input,
      if (deviceId != null && deviceId.isNotEmpty) 'device_id': deviceId,
    });
  }

  void cancelTask(String taskId) =>
      _send({'type': 'task.control', 'task_id': taskId, 'action': 'cancel'});

  void requestProjects({required String requestId, String? deviceId}) =>
      _send({
        'type': 'projects.request',
        'request_id': requestId,
        if (deviceId != null && deviceId.isNotEmpty) 'device_id': deviceId,
      });

  void stop() => _host.stop();
}
