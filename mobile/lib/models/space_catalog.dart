import 'package:flutter/material.dart';

class SpaceItemSpec {
  final String key;
  final String label;
  final IconData icon;
  final Color color;
  final int? badge;

  const SpaceItemSpec({
    required this.key,
    required this.label,
    required this.icon,
    required this.color,
    this.badge,
  });
}

class SpaceGroupSpec {
  final String title;
  final List<SpaceItemSpec> items;

  const SpaceGroupSpec({required this.title, required this.items});
}

SpaceItemSpec _item(
  String key,
  String label,
  IconData icon,
  Color color,
  int count,
) {
  return SpaceItemSpec(
    key: key,
    label: label,
    icon: icon,
    color: color,
    badge: count > 0 ? count : null,
  );
}

/// Builds the fixed «空间» catalogue. Group order is part of the product.
List<SpaceGroupSpec> buildSpaceCatalog({
  int mailCount = 0,
  int dingtalkCount = 0,
  int notificationCount = 0,
  int scheduleCount = 0,
  int todoCount = 0,
  int projectCount = 0,
  int fileCount = 0,
  int sourceCount = 0,
}) {
  const blue = Color(0xFF2E7CF6);
  const orange = Color(0xFFF97316);
  const green = Color(0xFF0FA97A);
  const purple = Color(0xFF7C5CF6);
  const grey = Color(0xFF6F7D92);

  return [
    SpaceGroupSpec(
      title: '沟通',
      items: [
        _item('mail', '邮件', Icons.mail_outline_rounded, blue, mailCount),
        _item('dingtalk', '钉钉', Icons.chat_outlined, orange, dingtalkCount),
        _item('notifications', '通知', Icons.notifications_none_rounded, green,
            notificationCount),
      ],
    ),
    SpaceGroupSpec(
      title: '工作',
      items: [
        _item('schedule', '日程', Icons.event_outlined, blue, scheduleCount),
        const SpaceItemSpec(
          key: 'goals',
          label: '目标',
          icon: Icons.flag_outlined,
          color: purple,
        ),
        const SpaceItemSpec(
          key: 'minutes',
          label: '录音纪要',
          icon: Icons.mic_rounded,
          color: orange,
        ),
        const SpaceItemSpec(
          key: 'agent',
          label: 'AI 任务',
          icon: Icons.auto_awesome_motion_rounded,
          color: purple,
        ),
        _item('todo', '待办', Icons.check_circle_outline_rounded, orange,
            todoCount),
        _item('projects', '项目', Icons.grid_view_outlined, purple, projectCount),
        _item('insights', '回顾', Icons.insights_outlined, green, 0),
        _item('automation', '自动化', Icons.auto_mode_rounded, grey, 0),
      ],
    ),
    SpaceGroupSpec(
      title: '内容',
      items: [
        _item('files', '文件', Icons.folder_outlined, grey, fileCount),
        const SpaceItemSpec(
          key: 'notes',
          label: '笔记',
          icon: Icons.article_outlined,
          color: green,
        ),
        _item('sources', '资讯', Icons.dynamic_feed_rounded, purple, sourceCount),
        const SpaceItemSpec(
          key: 'music',
          label: '音乐',
          icon: Icons.music_note_outlined,
          color: orange,
        ),
      ],
    ),
    SpaceGroupSpec(
      title: '更多',
      items: [
        const SpaceItemSpec(
          key: 'device',
          label: '设备',
          icon: Icons.devices_other_outlined,
          color: green,
        ),
        const SpaceItemSpec(
          key: 'machine',
          label: '本地机器',
          icon: Icons.computer_outlined,
          color: green,
        ),
        const SpaceItemSpec(
          key: 'sessions',
          label: 'OpenCode',
          icon: Icons.terminal_rounded,
          color: blue,
        ),
        const SpaceItemSpec(
          key: 'books',
          label: '书库',
          icon: Icons.menu_book_outlined,
          color: orange,
        ),
        const SpaceItemSpec(
          key: 'lab',
          label: '实验室',
          icon: Icons.science_outlined,
          color: grey,
        ),
      ],
    ),
  ];
}
