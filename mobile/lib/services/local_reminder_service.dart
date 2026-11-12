import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'api_service.dart';

/// Schedules on-device reminders for schedule events and todos, so they still
/// fire when the app is closed. iOS uses UNUserNotificationCenter; Android uses
/// the local notifications channel.
class LocalReminderService {
  static final LocalReminderService _instance = LocalReminderService._();
  factory LocalReminderService() => _instance;
  LocalReminderService._();

  final _plugin = FlutterLocalNotificationsPlugin();
  bool _initialized = false;
  bool _permissionRequested = false;
  String? _pendingLaunchPayload;

  /// Called when the user taps a local notification. Payload format is
  /// documented by the caller (meeting/opencode deep links).
  void Function(String payload)? onTap;

  static const _scheduleBase = 1000;
  static const _todoBase = 2000;
  // iOS keeps at most 64 pending local notifications, so stay under that.
  static const _maxPerType = 30;

  Future<void> init() async {
    if (_initialized) return;
    tzdata.initializeTimeZones();
    const ios = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
      defaultPresentAlert: true,
      defaultPresentBadge: true,
      defaultPresentSound: true,
    );
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _plugin.initialize(
      const InitializationSettings(iOS: ios, android: android),
      onDidReceiveNotificationResponse: (response) {
        final payload = response.payload;
        if (payload != null && payload.isNotEmpty) onTap?.call(payload);
      },
    );
    try {
      final launch = await _plugin.getNotificationAppLaunchDetails();
      if (launch?.didNotificationLaunchApp == true) {
        final payload = launch?.notificationResponse?.payload;
        if (payload != null && payload.isNotEmpty) {
          _pendingLaunchPayload = payload;
        }
      }
    } catch (_) {}
    _initialized = true;
  }

  Future<bool> _ensurePermission() async {
    if (_permissionRequested) return true;
    _permissionRequested = true;
    try {
      final ios = _plugin.resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin>();
      if (ios != null) {
        return await ios.requestPermissions(
              alert: true,
              badge: true,
              sound: true,
            ) ??
            false;
      }
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      if (android != null) {
        return await android.requestNotificationsPermission() ?? false;
      }
    } catch (_) {}
    return false;
  }

  NotificationDetails get _details => const NotificationDetails(
        iOS: DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
        android: AndroidNotificationDetails(
          'omniaide_reminders',
          'OmniAide 提醒',
          channelDescription: '日程与待办提醒',
          importance: Importance.high,
          priority: Priority.high,
        ),
      );

  /// Ask for notification permission (idempotent). Called when the user starts
  /// their first coding task so completion alerts can reach them later.
  Future<bool> ensurePermission() async {
    await init();
    return _ensurePermission();
  }

  /// Show an immediate local notification, e.g. when a coding session
  /// finishes while the app is in the background.
  String? takeLaunchPayload() {
    final payload = _pendingLaunchPayload;
    _pendingLaunchPayload = null;
    return payload;
  }

  Future<void> showNow({
    required String title,
    required String body,
    int id = 3001,
    String? payload,
  }) async {
    try {
      await init();
      if (!await _ensurePermission()) return;
      await _plugin.show(
        id,
        title,
        body,
        const NotificationDetails(
          iOS: DarwinNotificationDetails(
            presentAlert: true,
            presentBadge: true,
            presentSound: true,
          ),
          android: AndroidNotificationDetails(
            'omniaide_coding',
            'OmniAide 任务提醒',
            channelDescription: '编程与会议任务完成提醒',
            importance: Importance.high,
            priority: Priority.high,
          ),
        ),
        payload: payload,
      );
    } catch (_) {}
  }

  Future<void> syncSchedule(List<Map<String, dynamic>> events) async {
    try {
      final now = DateTime.now();
      final pending = <(DateTime, String)>[];
      for (final event in events) {
        if (pending.length >= _maxPerType) break;
        final when = DateTime.tryParse((event['start_time'] ?? '').toString());
        if (when == null) continue;
        final local = when.isUtc ? when.toLocal() : when;
        final fireAt = local.subtract(const Duration(minutes: 10));
        if (!fireAt.isAfter(now)) continue;
        pending.add((fireAt, (event['title'] ?? '日程').toString()));
      }
      if (pending.isEmpty) return;

      await init();
      if (!await _ensurePermission()) return;
      for (var i = 0; i < _maxPerType; i++) {
        await _plugin.cancel(_scheduleBase + i);
      }
      for (var i = 0; i < pending.length; i++) {
        final item = pending[i];
        await _plugin.zonedSchedule(
          _scheduleBase + i,
          '日程提醒',
          item.$2,
          _tz(item.$1),
          _details,
          androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        );
      }
    } catch (_) {}
  }

  Future<void> syncTodos(List<Map<String, dynamic>> items) async {
    try {
      final now = DateTime.now();
      final pending = <(DateTime, String)>[];
      for (final item in items) {
        if (pending.length >= _maxPerType) break;
        if (item['status'] == 'done' || item['completed'] == true) continue;
        final due = DateTime.tryParse((item['due_date'] ?? '').toString());
        if (due == null) continue;
        final local = due.isUtc ? due.toLocal() : due;
        final fireAt = local.subtract(const Duration(minutes: 10));
        if (!fireAt.isAfter(now)) continue;
        pending.add((fireAt, (item['title'] ?? '待办').toString()));
      }
      if (pending.isEmpty) return;

      await init();
      if (!await _ensurePermission()) return;
      for (var i = 0; i < _maxPerType; i++) {
        await _plugin.cancel(_todoBase + i);
      }
      for (var i = 0; i < pending.length; i++) {
        final item = pending[i];
        await _plugin.zonedSchedule(
          _todoBase + i,
          '待办提醒',
          item.$2,
          _tz(item.$1),
          _details,
          androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        );
      }
    } catch (_) {}
  }

  /// Fetch the next 30 days and reschedule everything. Safe to call on start.
  Future<void> syncAll() async {
    try {
      final now = DateTime.now();
      final end = now.add(const Duration(days: 30));
      final results = await Future.wait([
        ApiService().listScheduleEvents(
          start: now.toUtc().toIso8601String(),
          end: end.toUtc().toIso8601String(),
        ),
        ApiService().listTodoItems(status: 'pending', pageSize: 200),
      ]);
      await syncSchedule(results[0]);
      await syncTodos(results[1]);
    } catch (_) {}
  }

  tz.TZDateTime _tz(DateTime local) =>
      tz.TZDateTime.from(local.toUtc(), tz.UTC);
}
