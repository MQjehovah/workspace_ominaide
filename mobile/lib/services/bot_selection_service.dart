import 'package:shared_preferences/shared_preferences.dart';

/// Remembers which AI bot/role the user selected for chat.
class BotSelectionService {
  static final BotSelectionService _instance = BotSelectionService._();
  factory BotSelectionService() => _instance;
  BotSelectionService._();

  static const _idKey = 'chat.selectedBotId';
  static const _nameKey = 'chat.selectedBotName';

  int? botId;
  String? botName;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    botId = prefs.getInt(_idKey);
    botName = prefs.getString(_nameKey);
  }

  Future<void> select(int id, String name) async {
    botId = id;
    botName = name;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_idKey, id);
    await prefs.setString(_nameKey, name);
  }

  Future<void> clear() async {
    botId = null;
    botName = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_idKey);
    await prefs.remove(_nameKey);
  }
}
