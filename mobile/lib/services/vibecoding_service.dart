import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// WebSocket link to the backend `/ws/vibecoding` as role=mobile.
/// Broadcasts every server message (device.status / task.event /
/// tasks.snapshot / projects.response / dispatch.error / pong) and
/// auto-reconnects with exponential backoff.
class VibecodingService {
  WebSocket? _socket;
  Timer? _reconnectTimer;
  int _retry = 0;
  bool _connecting = false;

  final StreamController<Map<String, dynamic>> _events =
      StreamController<Map<String, dynamic>>.broadcast();

  final ValueNotifier<bool> connected = ValueNotifier<bool>(false);

  static final VibecodingService _instance = VibecodingService._();
  factory VibecodingService() => _instance;
  VibecodingService._();

  Stream<Map<String, dynamic>> get stream => _events.stream;

  Future<void> ensureConnected() async {
    if (connected.value || _connecting) return;
    await _connect();
  }

  Future<void> _connect() async {
    if (_connecting || connected.value) return;
    _connecting = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('token');
      final serverUrl = prefs.getString('serverUrl') ?? 'http://10.0.2.2:8000';
      if (token == null || token.isEmpty) {
        _connecting = false;
        return;
      }
      final wsUrl = serverUrl
          .replaceFirst('http://', 'ws://')
          .replaceFirst('https://', 'wss://');
      final socket =
          await WebSocket.connect('$wsUrl/ws/vibecoding?token=$token&role=mobile');
      _socket = socket;
      _retry = 0;
      _connecting = false;
      connected.value = true;
      socket.listen((data) {
        try {
          final msg = jsonDecode(data as String);
          if (msg is Map) _events.add(Map<String, dynamic>.from(msg));
        } catch (_) {}
      }, onDone: () {
        if (_socket == socket) _socket = null;
        connected.value = false;
        _scheduleReconnect();
      }, onError: (_) {
        if (_socket == socket) _socket = null;
        connected.value = false;
        _scheduleReconnect();
      });
    } catch (_) {
      _connecting = false;
      connected.value = false;
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_reconnectTimer != null) return;
    _retry++;
    final seconds = min(60, 3 * (1 << min(_retry, 4)));
    _reconnectTimer = Timer(Duration(seconds: seconds), () {
      _reconnectTimer = null;
      _connect();
    });
  }

  void _send(Map<String, dynamic> msg) {
    try {
      _socket?.add(jsonEncode(msg));
    } catch (_) {}
  }

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

  void stop() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    try {
      _socket?.close();
    } catch (_) {}
    _socket = null;
    connected.value = false;
  }
}
