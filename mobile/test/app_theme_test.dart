import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omniaide_mobile/theme/app_theme.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('mixWithWhite blends towards white', () {
    final mixed = mixWithWhite(const Color(0xFF000000), 0.5);
    expect((mixed.r * 255).round(), 128);
    expect((mixed.g * 255).round(), 128);
    expect((mixed.b * 255).round(), 128);
  });

  test('buildAppTheme applies seed to scheme and palette', () {
    const seed = Color(0xFF2E7CF6);
    final theme = buildAppTheme(
      seed: seed,
      brightness: Brightness.light,
      tintBackground: true,
    );
    expect(theme.colorScheme.primary.toARGB32(), seed.toARGB32());
    final palette = theme.extension<AppPalette>();
    expect(palette, isNotNull);
    expect(palette!.primary.toARGB32(), seed.toARGB32());
    expect(theme.scaffoldBackgroundColor, isNot(Colors.white));
  });

  test('tint off keeps a neutral background', () {
    final theme = buildAppTheme(
      seed: const Color(0xFFE0507F),
      brightness: Brightness.light,
      tintBackground: false,
    );
    expect(theme.scaffoldBackgroundColor, const Color(0xFFF6F8FC));
  });

  test('controller defaults', () {
    final controller = AppThemeController();
    expect(controller.seed.toARGB32(), const Color(0xFF2E7CF6).toARGB32());
    expect(controller.tintBackground, isTrue);
    expect(controller.mode, ThemeMode.system);
    expect(controller.fontScale, 1.0);
  });

  test('controller loads persisted values', () async {
    SharedPreferences.setMockInitialValues({
      'theme.seed': 0xFF0FA97A,
      'theme.tint': false,
      'theme.mode': 'dark',
      'theme.fontScale': 1.2,
    });
    final controller = AppThemeController();
    await controller.load();
    expect(controller.seed.toARGB32(), 0xFF0FA97A);
    expect(controller.tintBackground, isFalse);
    expect(controller.mode, ThemeMode.dark);
    expect(controller.fontScale, 1.2);
  });

  test('setters notify listeners and persist', () async {
    SharedPreferences.setMockInitialValues({});
    final controller = AppThemeController();
    var notifications = 0;
    controller.addListener(() => notifications++);

    await controller.setSeed(const Color(0xFFF97316));
    await controller.setTint(false);
    await controller.setMode(ThemeMode.light);
    await controller.setFontScale(1.3);

    expect(notifications, 4);
    expect(controller.seed.toARGB32(), 0xFFF97316);
    expect(controller.tintBackground, isFalse);
    expect(controller.mode, ThemeMode.light);
    expect(controller.fontScale, 1.3);

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getInt('theme.seed'), 0xFFF97316);
    expect(prefs.getBool('theme.tint'), isFalse);
    expect(prefs.getString('theme.mode'), 'light');
    expect(prefs.getDouble('theme.fontScale'), 1.3);
  });

  test('applyRemote applies cross-device values', () async {
    SharedPreferences.setMockInitialValues({});
    final controller = AppThemeController();
    await controller.applyRemote({
      'primary': '#0FA97A',
      'tint': false,
      'mode': 'dark',
      'font_scale': 1.2,
    });
    expect(controller.seed.toARGB32(), 0xFF0FA97A);
    expect(controller.tintBackground, isFalse);
    expect(controller.mode, ThemeMode.dark);
    expect(controller.fontScale, 1.2);
    expect(controller.hasLocalSettings, isTrue);
  });

  test('font scale is clamped to the accessible range', () async {
    SharedPreferences.setMockInitialValues({});
    final controller = AppThemeController();
    await controller.setFontScale(3.0);
    expect(controller.fontScale, 1.3);
    await controller.setFontScale(0.2);
    expect(controller.fontScale, 0.9);
  });
}
