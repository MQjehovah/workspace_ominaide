/// Helpers for the local wall-clock timestamps returned by the schedule API.
DateTime? parseEventDate(dynamic value) {
  final raw = (value ?? '').toString();
  if (raw.isEmpty) return null;
  return DateTime.tryParse(raw)?.toLocal();
}

DateTime? eventStart(Map<String, dynamic> event) =>
    parseEventDate(event['start_time']);

DateTime? eventEnd(Map<String, dynamic> event) {
  final end = parseEventDate(event['end_time']);
  if (end != null) return end;
  return eventStart(event)?.add(const Duration(hours: 1));
}

bool eventHasEnded(Map<String, dynamic> event, [DateTime? now]) {
  final end = eventEnd(event);
  if (end == null) return false;
  return end.isBefore(now ?? DateTime.now());
}
