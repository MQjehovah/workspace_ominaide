import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/widgets/navigation_shell.dart';

void main() {
  testWidgets('shows four tabs and starts on workbench', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: NavigationShell(
          initialIndex: 1,
          pages: [
            Text('chat-page'),
            Text('workbench-page'),
            Text('space-page'),
            Text('me-page'),
          ],
        ),
      ),
    );

    expect(find.text('对话'), findsOneWidget);
    expect(find.text('工作台'), findsOneWidget);
    expect(find.text('空间'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);

    expect(find.text('workbench-page'), findsOneWidget);
    expect(find.text('chat-page'), findsNothing);
  });

  testWidgets('switches to space', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: NavigationShell(
          initialIndex: 1,
          pages: [
            Text('chat-page'),
            Text('workbench-page'),
            Text('space-page'),
            Text('me-page'),
          ],
        ),
      ),
    );

    await tester.tap(find.text('空间'));
    await tester.pumpAndSettle();

    expect(find.text('space-page'), findsOneWidget);
    expect(find.text('workbench-page'), findsNothing);
  });

  testWidgets('reports tab changes', (tester) async {
    var last = -1;
    await tester.pumpWidget(
      MaterialApp(
        home: NavigationShell(
          initialIndex: 1,
          onTabChanged: (value) => last = value,
          pages: const [
            Text('chat-page'),
            Text('workbench-page'),
            Text('space-page'),
            Text('me-page'),
          ],
        ),
      ),
    );

    await tester.tap(find.text('对话'));
    await tester.pumpAndSettle();
    expect(last, 0);
  });
}
