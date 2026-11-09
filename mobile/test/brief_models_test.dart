import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/models/cos_models.dart';

void main() {
  test('parses a daily brief', () {
    final brief = DailyBrief.fromJson({
      'day': '2026-11-06',
      'summary': '先过预算评审，再回复客户。',
      'prompts': ['准备预算评审', '回复客户'],
    });

    expect(brief.summary, '先过预算评审，再回复客户。');
    expect(brief.prompts, ['准备预算评审', '回复客户']);
  });

  test('missing brief fields do not throw', () {
    final brief = DailyBrief.fromJson({});
    expect(brief.summary, '');
    expect(brief.prompts, isEmpty);
  });

  test('parses weekly review', () {
    final review = WeeklyReview.fromJson({
      'period': {'start': '2026-10-31', 'end': '2026-11-06'},
      'summary': '本周完成 5 项待办。',
      'wins': ['预算评审'],
      'in_progress': ['周报'],
      'risks': ['客户确认'],
      'next_week': ['产品周会'],
      'stats': {'todos_done': 5},
    });

    expect(review.periodStart, '2026-10-31');
    expect(review.wins, ['预算评审']);
    expect(review.inProgress, ['周报']);
    expect(review.stats['todos_done'], 5);
  });
}
