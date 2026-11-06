String _str(dynamic value) => (value ?? '').toString().trim();

List<dynamic> _list(dynamic value) => value is List ? value : const [];

Map<String, dynamic> _map(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.map((k, v) => MapEntry(k.toString(), v));
  return const {};
}

class BriefItem {
  final String title;
  final String summary;
  final String source;
  final String link;
  final int? sourceId;
  final DateTime? time;

  const BriefItem({
    required this.title,
    this.summary = '',
    this.source = '',
    this.link = '',
    this.sourceId,
    this.time,
  });

  factory BriefItem.fromJson(Map<String, dynamic> json) {
    return BriefItem(
      title: _str(json['title']),
      summary: _str(json['summary']),
      source: _str(json['source']),
      link: _str(json['link']),
      sourceId: json['source_id'] is int ? json['source_id'] as int : null,
      time: DateTime.tryParse(_str(json['time'])),
    );
  }
}

class BriefSection {
  final String key;
  final String title;
  final List<BriefItem> items;

  const BriefSection({
    required this.key,
    required this.title,
    this.items = const [],
  });

  factory BriefSection.fromJson(Map<String, dynamic> json) {
    return BriefSection(
      key: _str(json['key']),
      title: _str(json['title']),
      items: _list(json['items'])
          .whereType<Map>()
          .map((e) => BriefItem.fromJson(_map(e)))
          .toList(),
    );
  }
}

class DailyBrief {
  final String day;
  final String summary;
  final List<String> focus;
  final List<BriefSection> sections;
  final Map<String, dynamic> stats;
  final String dingtalkStatus;

  const DailyBrief({
    required this.day,
    required this.summary,
    this.focus = const [],
    this.sections = const [],
    this.stats = const {},
    this.dingtalkStatus = '',
  });

  factory DailyBrief.fromJson(Map<String, dynamic> json) {
    final sources = _map(json['sources']);
    return DailyBrief(
      day: _str(json['day']),
      summary: _str(json['summary']),
      focus: _list(json['focus']).map(_str).where((e) => e.isNotEmpty).toList(),
      sections: _list(json['sections'])
          .whereType<Map>()
          .map((e) => BriefSection.fromJson(_map(e)))
          .toList(),
      stats: _map(json['stats']),
      dingtalkStatus: _str(sources['dingtalk']),
    );
  }

  BriefSection? section(String key) {
    for (final section in sections) {
      if (section.key == key) return section;
    }
    return null;
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
    this.link = '',
    this.time,
  });

  factory TriageItem.fromJson(Map<String, dynamic> json) {
    return TriageItem(
      id: _str(json['id']),
      source: _str(json['source']),
      sourceId: json['source_id'] is int ? json['source_id'] as int : null,
      title: _str(json['title']),
      summary: _str(json['summary']),
      from: _str(json['from']),
      priority: _str(json['priority']).isEmpty ? 'normal' : _str(json['priority']),
      needsReply: json['needs_reply'] == true,
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
