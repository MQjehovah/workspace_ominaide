import 'package:flutter/material.dart';

const Color kBrand = Color(0xFF007AFF);
const Color kBrandDark = Color(0xFF0A84FF);
const Color kBgLight = Color(0xFFF5F6F8);
const Color kCardLight = Colors.white;

ThemeData buildLightTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: kBrand);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: kBgLight,
    appBarTheme: AppBarTheme(
      backgroundColor: kBgLight,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Color(0xFF1F2937)),
      iconTheme: const IconThemeData(color: Color(0xFF1F2937)),
    ),
    cardTheme: CardTheme(
      elevation: 0,
      color: kCardLight,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: Colors.grey.shade200)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      elevation: 8,
      indicatorColor: kBrand.withOpacity(0.12),
      labelTextStyle: MaterialStateProperty.all(const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
      iconTheme: MaterialStateProperty.resolveWith((states) {
        final selected = states.contains(MaterialState.selected);
        return IconThemeData(color: selected ? kBrand : Colors.grey.shade500);
      }),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.grey.shade300)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.grey.shade300)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: kBrand, width: 1.5)),
    ),
    listTileTheme: const ListTileThemeData(contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 2)),
    dividerTheme: DividerThemeData(color: Colors.grey.shade200),
  );
}

ThemeData buildDarkTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: kBrandDark, brightness: Brightness.dark);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xFF111318),
    cardTheme: CardTheme(
      elevation: 0,
      color: const Color(0xFF1A1D24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: Color(0xFF2A2E37))),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: const Color(0xFF1A1D24),
      elevation: 8,
      indicatorColor: kBrandDark.withOpacity(0.2),
      labelTextStyle: MaterialStateProperty.all(const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
      iconTheme: MaterialStateProperty.resolveWith((states) {
        final selected = states.contains(MaterialState.selected);
        return IconThemeData(color: selected ? kBrandDark : Colors.grey.shade500);
      }),
    ),
    appBarTheme: const AppBarTheme(
      elevation: 0,
      centerTitle: false,
      backgroundColor: Color(0xFF111318),
      titleTextStyle: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white),
      iconTheme: IconThemeData(color: Colors.white),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xFF1A1D24),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF2A2E37))),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF2A2E37))),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: kBrandDark, width: 1.5)),
    ),
    dividerTheme: const DividerThemeData(color: Color(0xFF2A2E37)),
  );
}
