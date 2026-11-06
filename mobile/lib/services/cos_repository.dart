import '../models/cos_models.dart';
import 'api_service.dart';

/// Small in-memory cache for expensive cross-page aggregates.
///
/// Workbench and 空间 both need triage and the daily brief; without this they
/// fire the same aggregation twice on every cold start.
class CosRepository {
  static const _ttl = Duration(seconds: 60);

  DailyBrief? _brief;
  DateTime? _briefAt;
  Future<DailyBrief?>? _briefFuture;

  TriageSnapshot? _triage;
  DateTime? _triageAt;
  Future<TriageSnapshot?>? _triageFuture;

  static final CosRepository instance = CosRepository._();
  CosRepository._();

  Future<DailyBrief?> getDailyBrief({bool force = false}) {
    if (!force && _brief != null && _isFresh(_briefAt)) return Future.value(_brief);
    if (_briefFuture != null) return _briefFuture!;
    final future = _loadBrief();
    _briefFuture = future;
    return future;
  }

  Future<DailyBrief?> _loadBrief() async {
    try {
      final brief = await ApiService().getDailyBrief();
      if (brief != null) {
        _brief = brief;
        _briefAt = DateTime.now();
      }
      return brief ?? _brief;
    } catch (_) {
      return _brief;
    } finally {
      _briefFuture = null;
    }
  }

  Future<TriageSnapshot?> getTriage({bool force = false}) {
    if (!force && _triage != null && _isFresh(_triageAt)) return Future.value(_triage);
    if (_triageFuture != null) return _triageFuture!;
    final future = _loadTriage();
    _triageFuture = future;
    return future;
  }

  Future<TriageSnapshot?> _loadTriage() async {
    try {
      final triage = await ApiService().getTriage();
      if (triage != null) {
        _triage = triage;
        _triageAt = DateTime.now();
      }
      return triage ?? _triage;
    } catch (_) {
      return _triage;
    } finally {
      _triageFuture = null;
    }
  }

  bool _isFresh(DateTime? at) {
    if (at == null) return false;
    return DateTime.now().difference(at) < _ttl;
  }

  void invalidate() {
    _briefAt = null;
    _triageAt = null;
  }
}

final cosRepository = CosRepository.instance;
