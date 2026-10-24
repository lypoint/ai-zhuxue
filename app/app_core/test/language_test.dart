import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DemoScreen extends StatelessWidget {
  const DemoScreen({super.key});
  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr('家长端')), actions: const [LanguageButton()]),
      body: TextField(decoration: InputDecoration(labelText: tr('科目'))),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
  });
  tearDown(() => AppLanguage.I.select('zh-Hans'));

  test('all 78 catalogs preserve every placeholder', () async {
    final raw =
        jsonDecode(
              await rootBundle.loadString(
                'packages/app_core/assets/i18n/catalog.json',
              ),
            )
            as Map;
    final base = (raw['zh-Hans'] as Map).cast<String, String>();
    final parameters = RegExp(r'\{\d+\}');
    for (final locale in supportedAppLocales) {
      final translated = (raw[locale.toLanguageTag()] as Map)
          .cast<String, String>();
      expect(translated.keys.toSet(), base.keys.toSet());
      for (final source in base.keys) {
        expect(
          translated[source]!.trim().isNotEmpty,
          true,
          reason: '$locale: $source',
        );
        final original = parameters.allMatches(source).map((m) => m[0]).toList()
          ..sort();
        final result =
            parameters.allMatches(translated[source]!).map((m) => m[0]).toList()
              ..sort();
        expect(result, original, reason: '$locale: $source');
      }
    }
  });

  test(
    'system locale resolution handles Chinese script and regional variants',
    () {
      expect(
        AppLanguage.resolve(const Locale('zh', 'CN')).toLanguageTag(),
        'zh-Hans',
      );
      expect(
        AppLanguage.resolve(const Locale('zh', 'TW')).toLanguageTag(),
        'zh-Hant',
      );
      expect(
        AppLanguage.resolve(const Locale('zh', 'HK')).toLanguageTag(),
        'zh-Hant-HK',
      );
      expect(
        AppLanguage.resolve(
          const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        ).toLanguageTag(),
        'zh-Hant',
      );
      expect(
        AppLanguage.resolve(
          const Locale.fromSubtags(
            languageCode: 'zh',
            scriptCode: 'Hans',
            countryCode: 'TW',
          ),
        ).toLanguageTag(),
        'zh-Hans',
      );
      expect(
        AppLanguage.resolve(const Locale('es', 'MX')),
        const Locale('es', '419'),
      );
      expect(
        AppLanguage.resolve(const Locale('es', 'US')),
        const Locale('es', 'US'),
      );
      expect(
        AppLanguage.resolve(const Locale('fr', 'CA')),
        const Locale('fr', 'CA'),
      );
      expect(
        AppLanguage.resolve(const Locale('pt', 'PT')),
        const Locale('pt', 'PT'),
      );
      expect(
        AppLanguage.resolve(
          const Locale.fromSubtags(
            languageCode: 'fr',
            scriptCode: 'Latn',
            countryCode: 'CA',
          ),
        ),
        const Locale('fr', 'CA'),
      );
      expect(AppLanguage.resolve(const Locale('no')), const Locale('nb'));
      expect(AppLanguage.resolve(const Locale('xx')), const Locale('en'));
      expect(AppLanguage.resolve(const Locale('fr')), const Locale('fr', 'FR'));
      expect(supportedAppLocales.length, 78);
      expect(appLocaleNames.length, 78);
    },
  );

  test(
    'selection persists, can return to system, and keeps user placeholders untouched',
    () async {
      await AppLanguage.I.select('en');
      expect(
        (await SharedPreferences.getInstance()).getString('app_language'),
        'en',
      );
      expect(tr('{0} 的设备', ['张三']), "张三's device");
      expect(trMessage('暂时无法创建订单，请稍后重试'), isNot(contains('请')));
      expect(trMessage('用户自己写的正文'), '用户自己写的正文');
      final error = ApiException(429, '这位老师今日免费次数已用完，请通知家长购买会员后继续学习');
      expect(error.rawMessage, contains('免费次数'));
      expect(error.message, isNot(contains('免费次数')));
      await AppLanguage.I.select(null);
      expect(
        (await SharedPreferences.getInstance()).getString('app_language'),
        isNull,
      );
      await expectLater(AppLanguage.I.select('xx'), throwsArgumentError);
    },
  );

  testWidgets('changing language rebuilds an open route without losing input', (
    tester,
  ) async {
    await tester.pumpWidget(
      LanguageApp(
        builder: (locale) => MaterialApp(
          locale: locale,
          supportedLocales: supportedAppLocales,
          localizationsDelegates: appLocalizationDelegates,
          home: const DemoScreen(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(ErrorWidget), findsNothing);
    expect(find.byType(Scaffold), findsOneWidget);
    expect(AppLanguage.I.tag, 'zh-Hans');
    expect(find.text('家长端'), findsOneWidget);
    await tester.enterText(find.byType(TextField), '孩子自己的文字');
    await tester.tap(find.byIcon(Icons.language));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('English'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(find.text('Parent app'), findsOneWidget);
    expect(find.text('Subject'), findsOneWidget);
    expect(find.text('孩子自己的文字'), findsOneWidget);
    for (final locale in supportedAppLocales) {
      final tag = locale.toLanguageTag();
      await AppLanguage.I.select(tag);
      await tester.pumpAndSettle();
      expect(find.text(tr('家长端')), findsOneWidget);
      expect(
        Directionality.of(tester.element(find.byType(TextField))),
        ['ar', 'he', 'ur', 'fa'].contains(locale.languageCode)
            ? TextDirection.rtl
            : TextDirection.ltr,
      );
      expect(tester.takeException(), isNull, reason: tag);
      expect(find.text('孩子自己的文字'), findsOneWidget);
      expect(
        (await SharedPreferences.getInstance()).getString('app_language'),
        tag,
      );
    }
    await tester.tap(find.byIcon(Icons.language));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Монгол хэл'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Монгол хэл'));
    await tester.pumpAndSettle();
    expect(AppLanguage.I.tag, 'mn');
  });

  test(
    'both chat transports send the current canonical client language',
    () async {
      await AppLanguage.I.select('de');
      var requests = 0;
      final client = MockClient((request) async {
        requests++;
        expect(request.headers['Accept-Language'], 'de');
        expect(jsonDecode(request.body)['locale'], 'de');
        expect(jsonDecode(request.body)['content'], 'Explain fractions');
        return http.Response(
          request.url.path == '/chat'
              ? '{}'
              : 'event: done\ndata: {"message_id":1}\n\n',
          200,
        );
      });
      await http.runWithClient(() async {
        await Api.I.sendChat(null, 'Explain fractions');
        await Api.I.sendChatStream(null, 'Explain fractions');
      }, () => client);
      expect(requests, 2);
      client.close();
    },
  );
}
