import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A selectable brand colour shown in Appearance settings.
class ThemePreset {
  final String name;
  final Color color;

  const ThemePreset(this.name, this.color);
}

const List<ThemePreset> kThemePresets = [
  ThemePreset('晴空蓝', Color(0xFF2E7CF6)),
  ThemePreset('薄荷绿', Color(0xFF0FA97A)),
  ThemePreset('暖阳橙', Color(0xFFF97316)),
  ThemePreset('樱花粉', Color(0xFFE0507F)),
];

const Color kAccent = Color(0xFFFF7A59);
const Color kSuccess = Color(0xFF1F9D6B);
const Color kInkLight = Color(0xFF16233B);
const Color kMutedLight = Color(0xFF7C8AA5);
const Color kNeutralBackground = Color(0xFFF6F8FC);

/// Blend [color] towards white. 0.0 keeps the colour, 1.0 returns white.
Color mixWithWhite(Color color, double amount) {
  final t = amount.clamp(0.0, 1.0);
  int channel(double value) =>
      ((value + (1 - value) * t) * 255).round().clamp(0, 255);
  return Color.fromARGB(255, channel(color.r), channel(color.g), channel(color.b));
}

/// Design tokens that are not part of Material's [ColorScheme].
@immutable
class AppPalette extends ThemeExtension<AppPalette> {
  final Color primary;
  final Color primaryLight;
  final Color primarySoft;
  final Color background;
  final Color card;
  final Color ink;
  final Color muted;
  final Color line;
  final Color accent;
  final Color success;

  const AppPalette({
    required this.primary,
    required this.primaryLight,
    required this.primarySoft,
    required this.background,
    required this.card,
    required this.ink,
    required this.muted,
    required this.line,
    required this.accent,
    required this.success,
  });

  static const fallback = AppPalette(
    primary: Color(0xFF2E7CF6),
    primaryLight: Color(0xFF6AA8FF),
    primarySoft: Color(0xFFE8F1FF),
    background: Color(0xFFF2F7FF),
    card: Colors.white,
    ink: kInkLight,
    muted: kMutedLight,
    line: Color(0xFFE3ECF9),
    accent: kAccent,
    success: kSuccess,
  );

  static AppPalette of(BuildContext context) =>
      Theme.of(context).extension<AppPalette>() ?? fallback;

  @override
  AppPalette copyWith({
    Color? primary,
    Color? primaryLight,
    Color? primarySoft,
    Color? background,
    Color? card,
    Color? ink,
    Color? muted,
    Color? line,
    Color? accent,
    Color? success,
  }) {
    return AppPalette(
      primary: primary ?? this.primary,
      primaryLight: primaryLight ?? this.primaryLight,
      primarySoft: primarySoft ?? this.primarySoft,
      background: background ?? this.background,
      card: card ?? this.card,
      ink: ink ?? this.ink,
      muted: muted ?? this.muted,
      line: line ?? this.line,
      accent: accent ?? this.accent,
      success: success ?? this.success,
    );
  }

  @override
  AppPalette lerp(covariant AppPalette? other, double t) {
    if (other == null) return this;
    Color blend(Color a, Color b) => Color.lerp(a, b, t)!;
    return AppPalette(
      primary: blend(primary, other.primary),
      primaryLight: blend(primaryLight, other.primaryLight),
      primarySoft: blend(primarySoft, other.primarySoft),
      background: blend(background, other.background),
      card: blend(card, other.card),
      ink: blend(ink, other.ink),
      muted: blend(muted, other.muted),
      line: blend(line, other.line),
      accent: blend(accent, other.accent),
      success: blend(success, other.success),
    );
  }
}

ThemeData buildAppTheme({
  required Color seed,
  required Brightness brightness,
  bool tintBackground = true,
}) {
  final isDark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: seed,
    brightness: brightness,
  ).copyWith(
    primary: seed,
    onPrimary: ThemeData.estimateBrightnessForColor(seed) == Brightness.dark
        ? Colors.white
        : Colors.black,
  );

  final background = isDark
      ? const Color(0xFF111318)
      : (tintBackground ? mixWithWhite(seed, 0.93) : kNeutralBackground);
  final card = isDark ? const Color(0xFF1A1D24) : Colors.white;
  final ink = isDark ? Colors.white : kInkLight;
  final muted = isDark ? const Color(0xFF9AA3B2) : kMutedLight;
  final line = isDark ? const Color(0xFF2A2E37) : mixWithWhite(seed, 0.82);

  final palette = AppPalette(
    primary: seed,
    primaryLight: mixWithWhite(seed, 0.32),
    primarySoft: isDark
        ? Color.lerp(seed, const Color(0xFF1A1D24), 0.78)!
        : mixWithWhite(seed, 0.88),
    background: background,
    card: card,
    ink: ink,
    muted: muted,
    line: line,
    accent: kAccent,
    success: kSuccess,
  );

  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: background,
    canvasColor: background,
  );

  return base.copyWith(
    extensions: [palette],
    appBarTheme: AppBarTheme(
      backgroundColor: background,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        fontSize: 19,
        fontWeight: FontWeight.w800,
        letterSpacing: -0.4,
        color: ink,
      ),
      iconTheme: IconThemeData(color: ink),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: card,
      surfaceTintColor: Colors.transparent,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: line),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: card,
      elevation: 0,
      height: 66,
      indicatorColor: mixWithWhite(seed, 0.86),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return TextStyle(
          fontSize: 11,
          fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
          color: selected ? seed : muted,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return IconThemeData(
          size: 22,
          color: selected ? seed : muted,
        );
      }),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: card,
      hintStyle: TextStyle(color: muted, fontSize: 13),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: seed, width: 1.4),
      ),
    ),
    dividerTheme: DividerThemeData(color: line, thickness: 1, space: 1),
    listTileTheme: const ListTileThemeData(
      contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 2),
    ),
    textTheme: base.textTheme.apply(bodyColor: ink, displayColor: ink),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: ink,
      contentTextStyle: TextStyle(color: isDark ? kInkLight : Colors.white),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}

/// Holds the user's appearance choices and persists them locally.
class AppThemeController extends ChangeNotifier {
  static const _seedKey = 'theme.seed';
  static const _tintKey = 'theme.tint';
  static const _modeKey = 'theme.mode';
  static const _fontKey = 'theme.fontScale';

  Color _seed = kThemePresets.first.color;
  bool _tintBackground = true;
  ThemeMode _mode = ThemeMode.system;
  double _fontScale = 1.0;
  bool _hasLocalSettings = false;

  Color get seed => _seed;
  bool get tintBackground => _tintBackground;
  ThemeMode get mode => _mode;
  double get fontScale => _fontScale;
  bool get hasLocalSettings => _hasLocalSettings;

  ThemeData get light => buildAppTheme(
        seed: _seed,
        brightness: Brightness.light,
        tintBackground: _tintBackground,
      );

  ThemeData get dark => buildAppTheme(
        seed: _seed,
        brightness: Brightness.dark,
        tintBackground: _tintBackground,
      );

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _hasLocalSettings = prefs.containsKey(_seedKey) ||
        prefs.containsKey(_tintKey) ||
        prefs.containsKey(_modeKey) ||
        prefs.containsKey(_fontKey);
    final seedValue = prefs.getInt(_seedKey);
    if (seedValue != null) _seed = Color(seedValue);
    _tintBackground = prefs.getBool(_tintKey) ?? true;
    final modeValue = prefs.getString(_modeKey);
    _mode = ThemeMode.values.firstWhere(
      (value) => value.name == modeValue,
      orElse: () => ThemeMode.system,
    );
    _fontScale = (prefs.getDouble(_fontKey) ?? 1.0).clamp(0.9, 1.3);
    notifyListeners();
  }

  /// Apply a newer cross-device snapshot without writing it back immediately.
  Future<void> applyRemote(Map<String, dynamic> settings) async {
    final primary = settings['primary'];
    if (primary is String && primary.startsWith('#') && primary.length == 7) {
      final value = int.tryParse(primary.substring(1), radix: 16);
      if (value != null) _seed = Color(0xFF000000 | value);
    }
    final tint = settings['tint'];
    if (tint is bool) _tintBackground = tint;
    final mode = settings['mode'];
    if (mode is String) {
      _mode = ThemeMode.values.firstWhere(
        (value) => value.name == mode,
        orElse: () => _mode,
      );
    }
    final font = settings['font_scale'];
    if (font is num) _fontScale = font.toDouble().clamp(0.9, 1.3);
    _hasLocalSettings = true;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_seedKey, _seed.toARGB32());
    await prefs.setBool(_tintKey, _tintBackground);
    await prefs.setString(_modeKey, _mode.name);
    await prefs.setDouble(_fontKey, _fontScale);
  }

  Future<void> setSeed(Color value, {bool notify = true}) async {
    _seed = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_seedKey, value.toARGB32());
    if (notify) notifyListeners();
  }

  Future<void> setTint(bool value, {bool notify = true}) async {
    _tintBackground = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_tintKey, value);
    if (notify) notifyListeners();
  }

  Future<void> setMode(ThemeMode value, {bool notify = true}) async {
    _mode = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_modeKey, value.name);
    if (notify) notifyListeners();
  }

  Future<void> setFontScale(double value, {bool notify = true}) async {
    _fontScale = value.clamp(0.9, 1.3);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble(_fontKey, _fontScale);
    if (notify) notifyListeners();
  }
}

final appTheme = AppThemeController();
