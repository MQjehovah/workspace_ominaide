import 'package:shared_preferences/shared_preferences.dart';

/// Tracks when a section was last opened so badges only show genuinely new
/// items instead of the total number of rows.
class SeenStateService {
  static final SeenStateService _instance = SeenStateService._();
  factory SeenStateService() => _instance;
  SeenStateService._();

  static const _filesSeenKey = 'space.files_seen_at';

  Future<DateTime?> filesSeenAt() async {
    final prefs = await SharedPreferences.getInstance();
    final ts = prefs.getInt(_filesSeenKey);
    return ts == null ? null : DateTime.fromMillisecondsSinceEpoch(ts);
  }

  Future<void> markFilesSeen([DateTime? at]) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(
      _filesSeenKey,
      (at ?? DateTime.now()).millisecondsSinceEpoch,
    );
  }
}
