import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The single multiplexed WebSocket (`/ws/host`, role=viewer) shared by all
/// mobile services. Every message on the wire carries a `channel` namespace;
/// consumers filter by channel. Auto-reconnects with exponential backoff.
class HostChannelService {
  WebSocket? _socket;
  Timer? _reconnectTimer;
  int _retry = 0;
  bool _connecting = false;

  final StreamController<Map<String, dynamic>> _events =
      StreamController<Map<String, dynamic>>.broadcast();

  final ValueNotifier<bool> connected = ValueNotifier<bool>(false);

  static final HostChannelService _instance = HostChannelService._();
  factory HostChannelService() => _instance;
  HostChannelService._();

  /// Broadcast stream of `{channel: "...", ...payload}` messages.
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
      final socket = await WebSocket.connect('$wsUrl/ws/host?token=$token&role=viewer');
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

  void send(String channel, Map<String, dynamic> msg) {
    try {
      _socket?.add(jsonEncode({'channel': channel, ...msg}));
    } catch (_) {}
  }

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
