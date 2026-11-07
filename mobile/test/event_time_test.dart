import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/models/cos_models.dart';
import 'package:omniaide_mobile/services/event_time.dart';

void main() {
  group('event time helpers', () {
    test('falls back to one hour when end_time is missing', () {
      final event = {
        'start_time': '2026-11-07T10:00:00',
      };
      expect(eventEnd(event), DateTime(2026, 11, 7, 11));
      expect(eventHasEnded(event, DateTime(2026, 11, 7, 10, 30)), isFalse);
      expect(eventHasEnded(event, DateTime(2026, 11, 7, 11, 1)), isTrue);
    });
  });

  group('triage snapshot', () {
    TriageItem item(String source, {bool read = false, String priority = 'normal'}) {
      return TriageItem.fromJson({
        'id': '$source:1',
        'source': source,
        'title': 'x',
        'priority': priority,
        'meta': {'read': read},
      });
    }

    test('pending excludes fyi and reads unread mail correctly', () {
      final snapshot = TriageSnapshot(
        groups: {
          'urgent': [item('mail', priority: 'urgent')],
          'needs_reply': [item('dingtalk')],
          'today': [item('todo')],
          'fyi': [item('mail', read: true), item('sources')],
        },
      );
      expect(snapshot.pendingCount, 3);
      expect(snapshot.unreadCount('mail'), 1);
    });
  });
}
