import '../models/cos_models.dart';
import 'api_service.dart';
import 'bot_selection_service.dart';

/// Small in-memory cache for the daily brief.
///
/// Workbench and 空间 both read the brief; without this they fire the same
/// aggregation twice on every cold start.
class CosRepository {
  static const _ttl = Duration(seconds: 60);

  DailyBrief? _brief;
  DateTime? _briefAt;
  int? _briefBotId;
  Future<DailyBrief?>? _briefFuture;

  static final CosRepository instance = CosRepository._();
  CosRepository._();

  Future<DailyBrief?> getDailyBrief({bool force = false}) {
    final botId = BotSelectionService().botId;
    if (!force &&
        _brief != null &&
        _briefBotId == botId &&
        _isFresh(_briefAt)) {
      return Future.value(_brief);
    }
    if (_briefFuture != null) return _briefFuture!;
    final future = _loadBrief(botId);
    _briefFuture = future;
    return future;
  }

  Future<DailyBrief?> _loadBrief(int? botId) async {
    try {
      final brief = await ApiService().getDailyBrief(botId: botId);
      if (brief != null) {
        _brief = brief;
        _briefAt = DateTime.now();
        _briefBotId = botId;
      }
      return brief ?? _brief;
    } catch (_) {
      return _brief;
    } finally {
      _briefFuture = null;
    }
  }

  bool _isFresh(DateTime? at) {
    if (at == null) return false;
    return DateTime.now().difference(at) < _ttl;
  }

  void invalidate() {
    _briefAt = null;
  }
}

final cosRepository = CosRepository.instance;
