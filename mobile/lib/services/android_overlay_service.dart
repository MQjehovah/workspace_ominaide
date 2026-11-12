import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Android system-wide floating button (SYSTEM_ALERT_WINDOW overlay).
///
/// Unlike the in-app bubble this stays above other apps. iOS has no equivalent,
/// so callers treat it as a no-op there.
class AndroidOverlayService {
  AndroidOverlayService._() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'quickCapture') {
        onQuickCapture?.call();
      }
      return null;
    });
  }

  static final AndroidOverlayService _instance = AndroidOverlayService._();
  factory AndroidOverlayService() => _instance;

  static const MethodChannel _channel = MethodChannel('omniaide/overlay');
  static const String _prefKey = 'android.overlay.enabled';

  /// Whether the native overlay service is currently showing.
  final ValueNotifier<bool> active = ValueNotifier<bool>(false);

  /// Called when the overlay is tapped in the idle state.
  void Function()? onQuickCapture;

  String _lastLabel = '';
  String _lastState = '';

  bool get supported => !kIsWeb && Platform.isAndroid;

  Future<bool> isEnabled() async {
    if (!supported) return false;
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_prefKey) ?? false;
  }

  Future<void> setEnabled(bool enabled) async {
    if (!supported) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_prefKey, enabled);
  }

  Future<bool> hasPermission() async {
    if (!supported) return false;
    try {
      return await _channel.invokeMethod<bool>('hasPermission') ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> requestPermission() async {
    if (!supported) return;
    try {
      await _channel.invokeMethod('requestPermission');
    } catch (_) {}
  }

  Future<bool> start({
    required String label,
    required String state,
  }) async {
    if (!supported) return false;
    try {
      final ok = await _channel.invokeMethod<bool>('start', {
        'label': label,
        'state': state,
      });
      active.value = ok == true;
      if (ok == true) {
        _lastLabel = label;
        _lastState = state;
      }
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  Future<void> update({
    required String label,
    required String state,
  }) async {
    if (!supported || !active.value) return;
    try {
      await _channel.invokeMethod('update', {
        'label': label,
        'state': state,
      });
    } catch (_) {}
  }

  Future<void> stop() async {
    if (!supported) return;
    try {
      await _channel.invokeMethod('stop');
    } catch (_) {}
    active.value = false;
    _lastLabel = '';
    _lastState = '';
  }

  Future<void> refreshActive() async {
    if (!supported) return;
    try {
      active.value = await _channel.invokeMethod<bool>('isActive') ?? false;
    } catch (_) {}
  }

  /// Start automatically after login if the user previously enabled it.
  Future<void> startIfEnabled() async {
    if (!supported || active.value) return;
    if (!await isEnabled()) return;
    if (!await hasPermission()) return;
    await start(label: '随手记', state: 'idle');
  }

  /// Push the latest run state to the native overlay. No-op when the feature
  /// is disabled or the platform is not Android.
  Future<void> sync({
    required String label,
    required String state,
  }) async {
    if (!supported) return;
    if (active.value && _lastLabel == label && _lastState == state) return;
    _lastLabel = label;
    _lastState = state;
    if (active.value) {
      await update(label: label, state: state);
      return;
    }
    if (!await isEnabled()) return;
    if (!await hasPermission()) return;
    await start(label: label, state: state);
  }
}
