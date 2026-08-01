import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Listens to the backend notification WebSocket and surfaces new
/// notifications to the UI via a callback.
class NotificationService {
  WebSocket? _socket;
  bool _connected = false;

  static final NotificationService _instance = NotificationService._();
  factory NotificationService() => _instance;
  NotificationService._();

  /// Start listening. [onNotification] is called with title/body when a new
  /// notification arrives.
  Future<void> start(Function(String title, String body) onNotification) async {
    if (_connected) return;
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');
    final serverUrl = prefs.getString('serverUrl') ?? 'http://10.0.2.2:8000';
    if (token == null || token.isEmpty) return;

    final wsUrl = serverUrl
        .replaceFirst('http://', 'ws://')
        .replaceFirst('https://', 'wss://');

    try {
      _socket = await WebSocket.connect('$wsUrl/ws/notifications?token=$token');
      _connected = true;
      _socket!.listen((data) {
        try {
          final json = jsonDecode(data as String);
          final title = (json['title'] as String?) ?? '新通知';
          final body = (json['body'] as String?) ?? '';
          onNotification(title, body);
        } catch (_) {}
      }, onDone: () => _connected = false, onError: (_) => _connected = false);
    } catch (_) {
      _connected = false;
    }
  }

  void stop() {
    try {
      _socket?.close();
    } catch (_) {}
    _socket = null;
    _connected = false;
  }
}
