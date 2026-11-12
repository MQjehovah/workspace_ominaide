import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

/// The single multiplexed WebSocket (`/ws/host`, role=viewer) shared by all
/// mobile services. Every message on the wire carries a `channel` namespace;
/// consumers filter by channel. Auto-reconnects with exponential backoff.
class HostChannelService {
  WebSocket? _socket;
  Timer? _reconnectTimer;
  int _retry = 0;
  bool _connecting = false;
  bool _stopped = false;

  final StreamController<Map<String, dynamic>> _events =
      StreamController<Map<String, dynamic>>.broadcast();

  final ValueNotifier<bool> connected = ValueNotifier<bool>(false);

  static final HostChannelService _instance = HostChannelService._();
  factory HostChannelService() => _instance;
  HostChannelService._();

  /// Broadcast stream of `{channel: "...", ...payload}` messages.
  Stream<Map<String, dynamic>> get stream => _events.stream;

  Future<void> ensureConnected() async {
    _stopped = false;
    if (connected.value || _connecting) return;
    await _connect();
  }

  /// The access token lives in secure storage; older builds kept it in
  /// SharedPreferences. Reading only the legacy key made the WS silently
  /// never connect, which surfaced as "离线" in every realtime screen.
  Future<String?> _readToken() async {
    try {
      final value =
          await const FlutterSecureStorage().read(key: 'omniaide.token');
      if (value != null && value.isNotEmpty) return value;
    } catch (_) {}
    final prefs = await SharedPreferences.getInstance();
    final legacy = prefs.getString('token');
    return legacy == null || legacy.isEmpty ? null : legacy;
  }

  Future<void> _connect() async {
    if (_stopped || _connecting || connected.value) return;
    _connecting = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (_stopped) {
        _connecting = false;
        return;
      }
      final token = await _readToken();
      final serverUrl = normalizeServerUrl(
        prefs.getString('serverUrl') ?? kDefaultServerUrl,
      );
      if (token == null || token.isEmpty) {
        _connecting = false;
        return;
      }
      final wsUrl = serverUrl
          .replaceFirst('http://', 'ws://')
          .replaceFirst('https://', 'wss://');
      final socket =
          await WebSocket.connect('$wsUrl/ws/host?token=$token&role=viewer');
      if (_stopped) {
        await socket.close();
        _connecting = false;
        return;
      }
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
        if (!_stopped) _scheduleReconnect();
      }, onError: (_) {
        if (_socket == socket) _socket = null;
        connected.value = false;
        if (!_stopped) _scheduleReconnect();
      });
    } catch (_) {
      _connecting = false;
      connected.value = false;
      if (!_stopped) _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_stopped || _reconnectTimer != null) return;
    _retry++;
    final seconds = min(60, 3 * (1 << min(_retry, 4)));
    _reconnectTimer = Timer(Duration(seconds: seconds), () {
      _reconnectTimer = null;
      _connect();
    });
  }

  /// Drop a possibly-dead socket and connect again. Used after the app returns
  /// from the background: iOS can suspend the socket without delivering a
  /// close event, leaving `connected` stuck at true.
  Future<void> reconnect() async {
    stop();
    await ensureConnected();
  }

  void send(String channel, Map<String, dynamic> msg) {
    try {
      _socket?.add(jsonEncode({'channel': channel, ...msg}));
    } catch (_) {}
  }

  void stop() {
    _stopped = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    try {
      _socket?.close();
    } catch (_) {}
    _socket = null;
    _connecting = false;
    connected.value = false;
  }
}
