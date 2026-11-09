import 'package:flutter_test/flutter_test.dart';

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
}
