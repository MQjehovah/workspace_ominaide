import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Small last-good cache for list screens. Lets the UI show data instantly and
/// stay usable when the network is slow or unavailable.
class LocalCacheService {
  static final LocalCacheService _instance = LocalCacheService._();
  factory LocalCacheService() => _instance;
  LocalCacheService._();

  static const _prefix = 'local_cache.';

  Future<void> writeJson(String key, Object value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_prefix$key', jsonEncode(value));
    await prefs.setInt(
      '$_prefix$key.ts',
      DateTime.now().millisecondsSinceEpoch,
    );
  }

  Future<List<Map<String, dynamic>>> readList(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('$_prefix$key');
    if (raw == null || raw.isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map>()
          .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<DateTime?> updatedAt(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final ts = prefs.getInt('$_prefix$key.ts');
    if (ts == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(ts);
  }
}
