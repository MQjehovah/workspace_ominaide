import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'theme/app_theme.dart';
import 'widgets/app_lock_gate.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await appTheme.load();
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
          theme: appTheme.light,
          darkTheme: appTheme.dark,
          themeMode: appTheme.mode,
          builder: (context, child) {
            final data = MediaQuery.of(context);
            return MediaQuery(
              data: data.copyWith(
                textScaler: TextScaler.linear(appTheme.fontScale),
              ),
              child: AppLockGate(
                child: child ?? const SizedBox.shrink(),
              ),
            );
          },
          home: const SplashScreen(),
        );
      },
    );
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
    if (ApiService().isLoggedIn && !appTheme.hasLocalSettings) {
      // Never block startup on an optional cross-device settings fetch.
      _pullRemoteAppearance();
    }
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => ApiService().isLoggedIn
            ? const HomeScreen()
            : const LoginScreen(),
      ),
    );
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
              child: const Icon(Icons.auto_awesome, size: 34, color: Colors.white),
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
