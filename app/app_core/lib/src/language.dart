import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

const supportedAppLocales = [
  Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
  Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
  Locale('en'),
  Locale('ja'),
  Locale('ko'),
  Locale('de'),
  Locale('es'),
];

const appLocalizationDelegates = [
  GlobalMaterialLocalizations.delegate,
  GlobalWidgetsLocalizations.delegate,
  GlobalCupertinoLocalizations.delegate,
];

/// Language is a device preference; it survives logout and never changes family data.
class AppLanguage extends ChangeNotifier with WidgetsBindingObserver {
  AppLanguage._();
  static final I = AppLanguage._();
  static const _preferenceKey = 'app_language';
  final Map<String, Map<String, String>> _catalog = {};
  final List<(String, RegExp)> _messagePatterns = [];
  final Map<String, String> _messageSources = {};
  Future<void>? _loading;
  bool _loaded = false;
  bool get loaded => _loaded;
  String? _selection;
  String? get selection => _selection;
  Locale get locale => _selection == null
      ? resolve(WidgetsBinding.instance.platformDispatcher.locale)
      : supportedAppLocales.firstWhere(
          (locale) => locale.toLanguageTag() == _selection,
        );
  String get tag => locale.toLanguageTag();

  static Locale resolve(Locale value) {
    if (value.languageCode == 'zh') {
      if (value.scriptCode == 'Hans') return supportedAppLocales[0];
      return supportedAppLocales[value.scriptCode == 'Hant' ||
              ['TW', 'HK', 'MO'].contains(value.countryCode)
          ? 1
          : 0];
    }
    return supportedAppLocales.firstWhere(
      (locale) => locale.languageCode == value.languageCode,
      orElse: () => const Locale('en'),
    );
  }

  Future<void> load() => _loading ??= _load();
  Future<void> _load() async {
    final raw =
        jsonDecode(
              await rootBundle.loadString(
                'packages/app_core/assets/i18n/catalog.json',
              ),
            )
            as Map<String, dynamic>;
    final messages = (raw.remove('_messages') as List).cast<String>();
    for (final entry in raw.entries) {
      _catalog[entry.key] = Map<String, String>.from(entry.value as Map);
      for (final translation in _catalog[entry.key]!.entries) {
        _messageSources[translation.value] = translation.key;
      }
    }
    for (final source in messages) {
      if (!source.contains(RegExp(r'\{\d+\}'))) continue;
      final templates = {
        source,
        for (final catalog in _catalog.values) catalog[source]!,
      };
      for (final template in templates) {
        final pattern = template.splitMapJoin(
          RegExp(r'\{(\d+)\}'),
          onMatch: (match) => '(?<p${match[1]}>.*?)',
          onNonMatch: RegExp.escape,
        );
        _messagePatterns.add((source, RegExp('^$pattern\$', dotAll: true)));
      }
    }
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_preferenceKey);
    _selection =
        supportedAppLocales.any((locale) => locale.toLanguageTag() == saved)
        ? saved
        : null;
    WidgetsBinding.instance.addObserver(this);
    _loaded = true;
    notifyListeners();
  }

  Future<void> select(String? tag) async {
    if (tag != null &&
        !supportedAppLocales.any((locale) => locale.toLanguageTag() == tag)) {
      throw ArgumentError.value(tag, 'tag', 'Unsupported language');
    }
    final prefs = await SharedPreferences.getInstance();
    if (tag == null) {
      await prefs.remove(_preferenceKey);
    } else {
      await prefs.setString(_preferenceKey, tag);
    }
    _selection = tag;
    notifyListeners();
  }

  @override
  void didChangeLocales(List<Locale>? locales) {
    if (_selection == null) notifyListeners();
  }

  /// Builds depend on Localizations so open routes also refresh after a switch.
  static void watch(BuildContext context) => Localizations.localeOf(context);

  String text(String source, [List<Object?> args = const []]) {
    final template = _loaded ? (_catalog[tag]?[source] ?? source) : source;
    return template.replaceAllMapped(RegExp(r'\{(\d+)\}'), (match) {
      final index = int.parse(match[1]!);
      return index < args.length ? '${args[index] ?? ''}' : match[0]!;
    });
  }

  /// Only system-authored templates are matched. User text and chat history stay original.
  String message(String source) {
    if (!_loaded) return source;
    if (_catalog[tag]?.containsKey(source) == true) return text(source);
    final original = _messageSources[source];
    if (original != null) return text(original);
    for (final (original, pattern) in _messagePatterns) {
      final match = pattern.firstMatch(source);
      if (match == null) continue;
      final indexes = RegExp(
        r'\{(\d+)\}',
      ).allMatches(original).map((m) => int.parse(m[1]!));
      final count = indexes.reduce((a, b) => a > b ? a : b) + 1;
      return text(
        original,
        List.generate(count, (i) => match.namedGroup('p$i')),
      );
    }
    return source;
  }
}

String tr(String source, [List<Object?> args = const []]) =>
    AppLanguage.I.text(source, args);
String trMessage(String source) => AppLanguage.I.message(source);
String localizedTeacherName(String name) =>
    name == 'AI 老师' || name == 'AI 学习助手' ? tr(name) : name;

/// Bootstraps translations in tests and in every independent channel entry.
class LanguageApp extends StatefulWidget {
  const LanguageApp({super.key, required this.builder});
  final Widget Function(Locale locale) builder;
  @override
  State<LanguageApp> createState() => _LanguageAppState();
}

class _LanguageAppState extends State<LanguageApp> {
  late final Future<void> _ready = AppLanguage.I.load();
  Widget _app() => ListenableBuilder(
    listenable: AppLanguage.I,
    builder: (context, _) => widget.builder(AppLanguage.I.locale),
  );
  @override
  Widget build(BuildContext context) => AppLanguage.I.loaded
      ? _app()
      : FutureBuilder<void>(
          future: _ready,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const SizedBox.shrink();
            }
            if (snapshot.hasError) return ErrorWidget(snapshot.error!);
            return _app();
          },
        );
}

class LanguageButton extends StatelessWidget {
  const LanguageButton({super.key});
  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    const names = [
      '简体中文',
      '繁體中文',
      'English',
      '日本語',
      '한국어',
      'Deutsch',
      'Español',
    ];
    return PopupMenuButton<String>(
      tooltip: tr('语言'),
      icon: const Icon(Icons.language),
      initialValue: AppLanguage.I.selection ?? 'system',
      onSelected: (value) =>
          AppLanguage.I.select(value == 'system' ? null : value),
      itemBuilder: (_) => [
        PopupMenuItem(value: 'system', child: Text(tr('跟随系统'))),
        for (var i = 0; i < supportedAppLocales.length; i++)
          PopupMenuItem(
            value: supportedAppLocales[i].toLanguageTag(),
            child: Text(names[i]),
          ),
      ],
    );
  }
}
