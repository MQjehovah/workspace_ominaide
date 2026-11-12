import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'services/bot_selection_service.dart';
import 'services/share_intent_service.dart';
import 'services/music_player_service.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/quick_capture_screen.dart';
import 'theme/app_theme.dart';
import 'widgets/app_lock_gate.dart';
import 'widgets/global_run_bubble.dart';

final _navigatorKey = GlobalKey<NavigatorState>();
final _messengerKey = GlobalKey<ScaffoldMessengerState>();
final _popupObserver = _PopupRouteObserver();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await appTheme.load();
  await ShareIntentService().init();
  MusicPlayerService().initialize();
  ShareIntentService().onCapture = (capture) {
    final navigator = _navigatorKey.currentState;
    if (navigator == null || !ApiService().isLoggedIn) return;
    navigator.push(
      MaterialPageRoute(
        builder: (_) => QuickCaptureScreen(
          initialText: capture.text,
          initialUrl: capture.url,
          initialImagePath: capture.imagePath,
        ),
      ),
    );
  };
  ApiService().onUnauthorized = () {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _messengerKey.currentState?.showSnackBar(
        const SnackBar(content: Text('登录已过期，请重新登录')),
      );
      _navigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
    });
  };
  runApp(const OmniAideApp());
}

class OmniAideApp extends StatelessWidget {
  const OmniAideApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: appTheme,
      builder: (context, _) {
        return MaterialApp(
          title: 'OmniAide',
          debugShowCheckedModeBanner: false,
          navigatorKey: _navigatorKey,
          scaffoldMessengerKey: _messengerKey,
          navigatorObservers: [_popupObserver],
          theme: appTheme.light,
          darkTheme: appTheme.dark,
          themeMode: appTheme.mode,
          builder: (context, child) {
            final data = MediaQuery.of(context);
            return MediaQuery(
              data: data.copyWith(
                textScaler: TextScaler.linear(appTheme.fontScale),
              ),
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
                child: AppLockGate(
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      child ?? const SizedBox.shrink(),
                      GlobalRunBubble(
                        navigatorKey: _navigatorKey,
                        popups: _popupObserver.popups,
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
          home: const SplashScreen(),
        );
      },
    );
  }
}

/// Counts open popup routes (bottom sheets and dialogs) so the floating run
/// bubble can hide while a modal is on screen instead of floating above it.
class _PopupRouteObserver extends NavigatorObserver {
  final ValueNotifier<int> popups = ValueNotifier<int>(0);

  void _bump(int delta) {
    popups.value = (popups.value + delta).clamp(0, 99).toInt();
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (route is PopupRoute) _bump(1);
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (route is PopupRoute) _bump(-1);
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (route is PopupRoute) _bump(-1);
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    if (newRoute is PopupRoute && oldRoute is! PopupRoute) {
      _bump(1);
    } else if (newRoute is! PopupRoute && oldRoute is PopupRoute) {
      _bump(-1);
    }
  }
}

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    await ApiService().loadToken();
    await BotSelectionService().load();
    if (ApiService().isLoggedIn && !appTheme.hasLocalSettings) {
      // Never block startup on an optional cross-device settings fetch.
      _pullRemoteAppearance();
    }
    if (!mounted) return;
    final shared =
        ApiService().isLoggedIn ? ShareIntentService().takePending() : null;
    ShareIntentService().markReady();
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) =>
            ApiService().isLoggedIn ? const HomeScreen() : const LoginScreen(),
      ),
    );
    if (shared != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _navigatorKey.currentState?.push(
          MaterialPageRoute(
            builder: (_) => QuickCaptureScreen(
              initialText: shared.text,
              initialUrl: shared.url,
              initialImagePath: shared.imagePath,
            ),
          ),
        );
      });
    }
  }

  Future<void> _pullRemoteAppearance() async {
    try {
      final remote = await ApiService().getAppearanceSettings();
      if (remote.isNotEmpty) await appTheme.applyRemote(remote);
    } catch (_) {
      // Offline: local defaults are still usable.
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
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
                borderRadius: BorderRadius.circular(26),
                boxShadow: [
                  BoxShadow(
                    color: palette.primary.withValues(alpha: 0.28),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child:
                  const Icon(Icons.auto_awesome, size: 34, color: Colors.white),
            ),
            const SizedBox(height: 18),
            Text(
              'OmniAide',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.6,
                color: palette.ink,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '你的随身幕僚',
              style: TextStyle(fontSize: 12, color: palette.muted),
            ),
          ],
        ),
      ),
    );
  }
}
