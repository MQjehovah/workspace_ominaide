import 'package:flutter/material.dart';

import '../services/app_lock_service.dart';
import '../theme/app_theme.dart';

/// Opaque lock overlay shown on startup and when the app returns from background.
class AppLockGate extends StatefulWidget {
  const AppLockGate({super.key, required this.child});

  final Widget child;

  @override
  State<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends State<AppLockGate> with WidgetsBindingObserver {
  bool _locked = false;
  bool _authenticating = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _maybeLock(authenticate: true);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _maybeLock(authenticate: false);
    }
  }

  Future<void> _maybeLock({required bool authenticate}) async {
    final enabled = await AppLockService().isEnabled();
    if (!mounted || !enabled) return;
    setState(() => _locked = true);
    if (authenticate) await _unlock();
  }

  Future<void> _unlock() async {
    if (_authenticating) return;
    setState(() => _authenticating = true);
    final ok = await AppLockService().authenticate();
    if (!mounted) return;
    setState(() {
      _authenticating = false;
      if (ok) _locked = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        if (_locked)
          Positioned.fill(
            child: _LockScreen(
              authenticating: _authenticating,
              onUnlock: _unlock,
            ),
          ),
      ],
    );
  }
}

class _LockScreen extends StatelessWidget {
  const _LockScreen({
    required this.authenticating,
    required this.onUnlock,
  });

  final bool authenticating;
  final VoidCallback onUnlock;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return ColoredBox(
      color: palette.background,
      child: SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 76,
                height: 76,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [palette.primaryLight, palette.primary],
                  ),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: const Icon(
                  Icons.lock_outline_rounded,
                  size: 34,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 18),
              Text(
                'OmniAide 已锁定',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '使用 Face ID 或设备密码解锁',
                style: TextStyle(fontSize: 12, color: palette.muted),
              ),
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: authenticating ? null : onUnlock,
                icon: authenticating
                    ? const SizedBox(
                        width: 15,
                        height: 15,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.face_rounded, size: 19),
                label: Text(authenticating ? '验证中…' : '解锁'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
