import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omniaide_mobile/services/opencode_run_monitor.dart';
import 'package:omniaide_mobile/services/vibecoding_service.dart';
import 'package:omniaide_mobile/widgets/global_run_bubble.dart';

void main() {
  test('formats short and long run durations', () {
    expect(formatRunDuration(const Duration(seconds: 9)), '0:09');
    expect(formatRunDuration(const Duration(minutes: 2, seconds: 31)), '2:31');
    expect(
      formatRunDuration(const Duration(hours: 1, minutes: 2, seconds: 3)),
      '1:02:03',
    );
  });

  testWidgets('bubble reflects running sessions and idle state',
      (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final navigatorKey = GlobalKey<NavigatorState>();
    final popups = ValueNotifier<int>(0);
    final monitor = OpenCodeRunMonitor();
    VibecodingService().connected.value = true;

    monitor.active.value = true;
    monitor.runs.value = [
      OpenCodeRun(
        machineId: 'mac',
        sessionId: 'ses_1',
        title: '修复登录',
        directory: '/tmp/project',
        startedAt: DateTime.now(),
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        builder: (context, child) => Stack(
          fit: StackFit.expand,
          children: [
            child ?? const SizedBox.shrink(),
            GlobalRunBubble(navigatorKey: navigatorKey, popups: popups),
          ],
        ),
        home: const Scaffold(body: SizedBox.expand()),
      ),
    );
    await tester.pump();

    expect(find.text('1 运行中'), findsOneWidget);

    monitor.runs.value = const [];
    await tester.pump();
    expect(find.text('随手记'), findsOneWidget);

    monitor.active.value = false;
    VibecodingService().connected.value = false;
    popups.value = 1;
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
