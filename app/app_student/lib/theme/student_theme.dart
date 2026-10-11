import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gpt_markdown/gpt_markdown.dart';

ThemeData studentTheme() {
  final base = appTheme(const Color(0xFF3D8B7A));
  return base.copyWith(
    extensions: [
      GptMarkdownThemeData(
        brightness: Brightness.light,
        h1: const TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        h2: const TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        h3: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        h4: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        h5: const TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        h6: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          height: 1.4,
        ),
        linkColor: base.colorScheme.primary,
      ),
    ],
    scaffoldBackgroundColor: const Color(0xFFF4F7F5),
    appBarTheme: base.appBarTheme.copyWith(
      backgroundColor: const Color(0xFFF4F7F5),
      systemOverlayStyle: SystemUiOverlayStyle.dark,
      titleTextStyle: TextStyle(
        color: base.colorScheme.onSurface,
        fontSize: 18,
        fontWeight: FontWeight.w700,
      ),
    ),
    cardTheme: base.cardTheme.copyWith(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: const BorderSide(color: Color(0xFFE3EBE6)),
      ),
    ),
    expansionTileTheme: const ExpansionTileThemeData(
      shape: Border(),
      collapsedShape: Border(),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: base.colorScheme.primary,
      foregroundColor: base.colorScheme.onPrimary,
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    drawerTheme: const DrawerThemeData(
      backgroundColor: Color(0xFFF4F7F5),
      surfaceTintColor: Colors.transparent,
    ),
    listTileTheme: ListTileThemeData(
      iconColor: base.colorScheme.primary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      selectedTileColor: const Color(0xFFE2EFE8),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
    ),
  );
}
