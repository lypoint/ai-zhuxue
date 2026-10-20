import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

ThemeData parentTheme() {
  final base = appTheme(const Color(0xFF28786B));
  final scheme = base.colorScheme.copyWith(
    primary: const Color(0xFF246C60),
    onPrimary: Colors.white,
    primaryContainer: const Color(0xFFDDEEE7),
    onPrimaryContainer: const Color(0xFF193F37),
    surface: Colors.white,
    onSurface: const Color(0xFF243831),
    onSurfaceVariant: const Color(0xFF63756D),
    outlineVariant: const Color(0xFFE4EBE6),
  );
  return base.copyWith(
    colorScheme: scheme,
    filledButtonTheme: FilledButtonThemeData(
      style: base.filledButtonTheme.style?.copyWith(
        minimumSize: const WidgetStatePropertyAll(Size(0, 48)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: base.outlinedButtonTheme.style?.copyWith(
        minimumSize: const WidgetStatePropertyAll(Size(0, 48)),
      ),
    ),
    scaffoldBackgroundColor: const Color(0xFFF5F7F4),
    textTheme: base.textTheme.apply(
      bodyColor: scheme.onSurface,
      displayColor: scheme.onSurface,
    ),
    appBarTheme: base.appBarTheme.copyWith(
      systemOverlayStyle: SystemUiOverlayStyle.dark,
      titleSpacing: 20,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 22,
        fontWeight: FontWeight.w700,
      ),
      iconTheme: IconThemeData(color: scheme.onSurfaceVariant),
    ),
    cardTheme: base.cardTheme.copyWith(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: base.inputDecorationTheme.copyWith(
      fillColor: const Color(0xFFF7F9F7),
    ),
    listTileTheme: ListTileThemeData(
      iconColor: scheme.primary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: scheme.primaryContainer,
      height: 76,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.onSurfaceVariant,
        ),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          color: states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.onSurfaceVariant,
          fontSize: 12,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w700
              : FontWeight.w500,
        ),
      ),
    ),
  );
}
