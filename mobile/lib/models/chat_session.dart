class ChatSession {
  final String id;
  final String title;
  final DateTime? updatedAt;

  const ChatSession({
    required this.id,
    required this.title,
    this.updatedAt,
  });

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    final id = (json['session_id'] ?? json['id'] ?? '').toString();
    final rawTitle = (json['title'] ?? '').toString().trim();
    final rawTime = (json['updated_at'] ?? json['created_at'] ?? '').toString();
    return ChatSession(
      id: id,
      title: rawTitle.isEmpty ? '新对话' : rawTitle,
      updatedAt: DateTime.tryParse(rawTime),
    );
  }
}

String relativeTimeLabel(DateTime? value, {DateTime? now}) {
  if (value == null) return '';
  final current = now ?? DateTime.now();
  final local = value.toLocal();
  final today = DateTime(current.year, current.month, current.day);
  final day = DateTime(local.year, local.month, local.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) {
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }
  if (diff == 1) return '昨天';
  if (local.year == current.year) {
    return '${local.month}月${local.day}日';
  }
  return '${local.year}/${local.month}/${local.day}';
}
