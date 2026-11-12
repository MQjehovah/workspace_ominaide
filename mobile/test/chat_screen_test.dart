import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/widgets/chat_bubble.dart';

void main() {
  testWidgets('renders a user message', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ChatBubble(role: 'user', text: '帮我看看今天的安排'),
        ),
      ),
    );
    expect(find.text('帮我看看今天的安排'), findsOneWidget);
  });

  testWidgets('shows typing indicator for empty streaming assistant',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ChatBubble(role: 'assistant', text: '', streaming: true),
        ),
      ),
    );
    expect(find.byKey(const Key('chat-typing')), findsOneWidget);
  });

  testWidgets('shows error and retry', (tester) async {
    var retried = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            role: 'assistant',
            text: '网络中断',
            error: true,
            onRetry: () => retried = true,
          ),
        ),
      ),
    );
    expect(find.text('回复失败'), findsOneWidget);
    await tester.tap(find.text('重新生成'));
    expect(retried, isTrue);
  });
}
