import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';

import 'api_service.dart';
import 'local_reminder_service.dart';

class _MeetingWatch {
  _MeetingWatch(this.title);

  final String title;
}

/// Watches meeting-minutes jobs outside the recording screen so long MOSS
/// transcriptions still notify when the user navigates away.
class MeetingJobMonitor with WidgetsBindingObserver {
  MeetingJobMonitor._();

  static final MeetingJobMonitor _instance = MeetingJobMonitor._();
  factory MeetingJobMonitor() => _instance;

  final Map<int, _MeetingWatch> _watches = <int, _MeetingWatch>{};
  Timer? _timer;
  bool _started = false;
  bool _polling = false;
  bool _appActive = true;

  void Function(Map<String, dynamic> job)? onCompleted;

  void start() {
    if (_started) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
  }

  void stop() {
    if (!_started) return;
    _started = false;
    _timer?.cancel();
    _timer = null;
    _watches.clear();
    WidgetsBinding.instance.removeObserver(this);
  }

  void track(int id, {String? title}) {
    if (!_started) start();
    final existing = _watches[id];
    _watches[id] = _MeetingWatch(
      (title == null || title.isEmpty ? existing?.title : title) ?? '会议纪要',
    );
    _ensureTimer();
    if (_appActive) {
      unawaited(LocalReminderService().ensurePermission());
    }
    unawaited(_poll());
  }

  void untrack(int id) {
    _watches.remove(id);
    if (_watches.isEmpty) {
      _timer?.cancel();
      _timer = null;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _appActive = true;
      unawaited(_poll());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _appActive = false;
    }
  }

  void _ensureTimer() {
    _timer ??= Timer.periodic(const Duration(seconds: 5), (_) {
      unawaited(_poll());
    });
  }

  Future<void> _poll() async {
    if (!_started || _polling || _watches.isEmpty) return;
    _polling = true;
    try {
      for (final id in _watches.keys.toList()) {
        final watch = _watches[id];
        if (watch == null) continue;
        try {
          final job = await ApiService().getMeetingMinutes(id);
          final status = (job['status'] ?? '').toString();
          if (status != 'done' && status != 'failed') continue;
          _watches.remove(id);
          final title = (job['title'] ?? watch.title).toString();
          if (_appActive) {
            onCompleted?.call(job);
          } else {
            final error = (job['error'] ?? '').toString();
            unawaited(
              LocalReminderService().showNow(
                title: status == 'done' ? '会议纪要已生成' : '会议纪要生成失败',
                body: status == 'failed' && error.isNotEmpty
                    ? '$title\n$error'
                    : title,
                id: 3100,
                payload: jsonEncode({
                  'kind': 'meeting',
                  'id': id,
                  'title': title,
                }),
              ),
            );
          }
        } catch (_) {
          // Keep watching; the job list is persisted server-side.
        }
      }
    } finally {
      _polling = false;
      if (_watches.isEmpty) {
        _timer?.cancel();
        _timer = null;
      }
    }
  }
}
