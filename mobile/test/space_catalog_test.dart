import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/models/space_catalog.dart';

void main() {
  test('groups stay in product order', () {
    final groups = buildSpaceCatalog();
    expect(groups.map((g) => g.title).toList(), ['沟通', '工作', '内容', '更多']);
  });

  test('badges use supplied counts and hide zero', () {
    final groups = buildSpaceCatalog(
      mailCount: 2,
      dingtalkCount: 3,
      notificationCount: 0,
      todoCount: 4,
    );
    final mail = groups
        .expand((g) => g.items)
        .firstWhere((item) => item.key == 'mail');
    final notification = groups
        .expand((g) => g.items)
        .firstWhere((item) => item.key == 'notifications');
    final todo = groups
        .expand((g) => g.items)
        .firstWhere((item) => item.key == 'todo');
    expect(mail.badge, 2);
    expect(notification.badge, isNull);
    expect(todo.badge, 4);
  });

  test('all business objects are present exactly once', () {
    final keys = buildSpaceCatalog()
        .expand((g) => g.items)
        .map((item) => item.key)
        .toList();
    expect(keys.toSet().length, keys.length);
    expect(
      keys,
      containsAll([
        'mail',
        'dingtalk',
        'notifications',
        'schedule',
        'minutes',
        'agent',
        'todo',
        'projects',
        'insights',
        'automation',
        'files',
        'notes',
        'sources',
        'music',
        'machine',
        'lab',
      ]),
    );
  });
}
