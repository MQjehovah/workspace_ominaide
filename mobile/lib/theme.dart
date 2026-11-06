import 'package:flutter/material.dart';

import 'theme/app_theme.dart';

/// Backwards-compatible theme helpers. New code should use [appTheme] and
/// [buildAppTheme] so the user's saved appearance choices apply.
const Color kBrand = Color(0xFF2E7CF6);
const Color kBrandDark = Color(0xFF6AA8FF);
const Color kBgLight = Color(0xFFF2F7FF);
const Color kCardLight = Colors.white;

ThemeData buildLightTheme() => buildAppTheme(
      seed: kBrand,
      brightness: Brightness.light,
      tintBackground: true,
    );

ThemeData buildDarkTheme() => buildAppTheme(
      seed: kBrand,
      brightness: Brightness.dark,
      tintBackground: true,
    );
