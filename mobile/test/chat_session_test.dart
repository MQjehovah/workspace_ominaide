import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/models/chat_session.dart';

void main() {
  test('parses a session payload', () {
    final session = ChatSession.fromJson({
      'session_id': 's1',
      'title': '预算评审准备',
      'updated_at': '2026-11-06T10:24:00',
    });
    expect(session.id, 's1');
    expect(session.title, '预算评审准备');
    expect(session.updatedAt, DateTime.utc(2026, 11, 6, 10, 24));
  });

  test('falls back to a readable title', () {
    final session = ChatSession.fromJson({'session_id': 's2', 'title': '   '});
    expect(session.title, '新对话');
  });

  test('formats relative times', () {
    final now = DateTime(2026, 11, 6, 15, 0);
    expect(relativeTimeLabel(DateTime(2026, 11, 6, 10, 24), now: now), '10:24');
    expect(relativeTimeLabel(DateTime(2026, 11, 5, 10, 24), now: now), '昨天');
    expect(relativeTimeLabel(DateTime(2026, 10, 2, 10, 24), now: now), '10月2日');
    expect(relativeTimeLabel(DateTime(2025, 12, 1), now: now), '2025/12/1');
    expect(relativeTimeLabel(null), '');
  });
}
