import 'package:flutter/foundation.dart';

/// Lightweight in-process refresh signals for tab pages that stay alive inside
/// the IndexedStack. Bumping a key refreshes the matching screen only.
class RefreshBus {
  RefreshBus._();

  static final Map<String, ValueNotifier<int>> _signals = {};

  static ValueNotifier<int> signal(String key) =>
      _signals.putIfAbsent(key, () => ValueNotifier<int>(0));

  static void bump(String key) => signal(key).value++;
}
