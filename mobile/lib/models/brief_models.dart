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
