String _str(dynamic value) => (value ?? '').toString().trim();

List<dynamic> _list(dynamic value) => value is List ? value : const [];

Map<String, dynamic> _map(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.map((k, v) => MapEntry(k.toString(), v));
  return const {};
}

class DailyBrief {
  final String day;
  final String summary;
  final List<String> prompts;

  const DailyBrief({
    required this.day,
    required this.summary,
    this.prompts = const [],
  });

  factory DailyBrief.fromJson(Map<String, dynamic> json) {
    return DailyBrief(
      day: _str(json['day']),
      summary: _str(json['summary']),
      prompts:
          _list(json['prompts']).map(_str).where((e) => e.isNotEmpty).toList(),
    );
  }
}

class WeeklyReview {
  final String periodStart;
  final String periodEnd;
  final String summary;
  final List<String> wins;
  final List<String> inProgress;
  final List<String> risks;
  final List<String> nextWeek;
  final Map<String, dynamic> stats;

  const WeeklyReview({
    required this.periodStart,
    required this.periodEnd,
    required this.summary,
    this.wins = const [],
    this.inProgress = const [],
    this.risks = const [],
    this.nextWeek = const [],
    this.stats = const {},
  });

  factory WeeklyReview.fromJson(Map<String, dynamic> json) {
    final period = _map(json['period']);
    return WeeklyReview(
      periodStart: _str(period['start']),
      periodEnd: _str(period['end']),
      summary: _str(json['summary']),
      wins: _list(json['wins']).map(_str).where((e) => e.isNotEmpty).toList(),
      inProgress: _list(json['in_progress']).map(_str).where((e) => e.isNotEmpty).toList(),
      risks: _list(json['risks']).map(_str).where((e) => e.isNotEmpty).toList(),
      nextWeek: _list(json['next_week']).map(_str).where((e) => e.isNotEmpty).toList(),
      stats: _map(json['stats']),
    );
  }

  static const empty = WeeklyReview(
    periodStart: '',
    periodEnd: '',
    summary: '本周还没有足够的数据。',
  );
}

class TriageItem {
  final String id;
  final String source;
  final int? sourceId;
  final String title;
  final String summary;
  final String from;
  final String priority;
  final bool needsReply;
  final bool read;
  final String link;
  final DateTime? time;

  const TriageItem({
    required this.id,
    required this.source,
    this.sourceId,
    required this.title,
    this.summary = '',
    this.from = '',
    this.priority = 'normal',
    this.needsReply = false,
    this.read = false,
    this.link = '',
    this.time,
  });

  factory TriageItem.fromJson(Map<String, dynamic> json) {
    final meta = _map(json['meta']);
    return TriageItem(
      id: _str(json['id']),
      source: _str(json['source']),
      sourceId: json['source_id'] is int ? json['source_id'] as int : null,
      title: _str(json['title']),
      summary: _str(json['summary']),
      from: _str(json['from']),
      priority: _str(json['priority']).isEmpty ? 'normal' : _str(json['priority']),
      needsReply: json['needs_reply'] == true,
      read: meta['read'] == true,
      link: _str(json['link']),
      time: DateTime.tryParse(_str(json['time'])),
    );
  }

  bool get isUrgent => priority == 'urgent';
}

class TriageSnapshot {
  final Map<String, List<TriageItem>> groups;
  final Map<String, int> counts;
  final String dingtalkStatus;
  final DateTime? generatedAt;

  const TriageSnapshot({
    this.groups = const {},
    this.counts = const {},
    this.dingtalkStatus = '',
    this.generatedAt,
  });

  factory TriageSnapshot.fromJson(Map<String, dynamic> json) {
    final rawGroups = _map(json['groups']);
    final groups = <String, List<TriageItem>>{};
    for (final entry in rawGroups.entries) {
      groups[entry.key] = _list(entry.value)
          .whereType<Map>()
          .map((e) => TriageItem.fromJson(_map(e)))
          .toList();
    }
    final rawCounts = _map(json['counts']);
    final counts = <String, int>{};
    for (final entry in rawCounts.entries) {
      final value = entry.value;
      counts[entry.key] = value is int ? value : int.tryParse('$value') ?? 0;
    }
    final sources = _map(json['sources']);
    return TriageSnapshot(
      groups: groups,
      counts: counts,
      dingtalkStatus: _str(sources['dingtalk']),
      generatedAt: DateTime.tryParse(_str(json['generated_at'])),
    );
  }

  static const empty = TriageSnapshot();

  int get total => counts['total'] ?? _all.length;
  int get urgentCount => counts['urgent'] ?? (groups['urgent']?.length ?? 0);
  int get needsReplyCount =>
      counts['needs_reply'] ?? (groups['needs_reply']?.length ?? 0);

  /// Actionable items only. Read mail and other FYI rows are not "待处理".
  List<TriageItem> get pendingItems => [
        ...?groups['urgent'],
        ...?groups['needs_reply'],
        ...?groups['today'],
      ];

  int get pendingCount => pendingItems.length;

  int unreadCount(String source) =>
      bySource(source).where((item) => !item.read).length;

  List<TriageItem> get _all =>
      groups.values.expand((items) => items).toList();

  List<TriageItem> bySource(String source) =>
      _all.where((item) => item.source == source).toList();

  Map<String, int> countsBySource() {
    final result = <String, int>{};
    for (final item in _all) {
      result[item.source] = (result[item.source] ?? 0) + 1;
    }
    return result;
  }
}
