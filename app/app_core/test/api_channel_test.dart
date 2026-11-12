import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:app_core/app_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() {
    Api.I.channel = '';
    debugDefaultTargetPlatformOverride = null;
  });

  test('all guardian registration paths send device snapshot', () async {
    SharedPreferences.setMockInitialValues({
      'installation_id': 'test-installation',
    });
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final paths = <String>[];
    await http.runWithClient(
      () async {
        await Api.I.registerGuardian('13912345678', '123456', '家长');
        await Api.I.guardianOneTap('test-one-tap-token');
        await Api.I.guardianGoogle('test-google-token');
      },
      () => MockClient((request) async {
        final device = jsonDecode(request.body)['registration_device'];
        expect(device['platform'], 'android');
        expect(device['installation_id'], 'test-installation');
        expect(device['os_version'], isA<String>());
        paths.add(request.url.path);
        return http.Response('{"token":"test-token","role":"guardian"}', 200);
      }),
    );
    expect(paths, [
      '/auth/guardian/register',
      '/auth/guardian/one-tap',
      '/auth/guardian/google',
    ]);
    Api.I.clearToken();
  });

  test('student channel defaults follow platform', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    expect(Api.I.appChannel, 'wechat');
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    expect(Api.I.appChannel, 'appstore');
  });

  test('teacher and subscription requests carry the package channel', () async {
    for (final channel in ['wechat', 'appstore', 'googleplay']) {
      Api.I.channel = channel;
      final paths = <String>[];
      await http.runWithClient(
        () async {
          await Api.I.teachers();
          await Api.I.subscription();
        },
        () => MockClient((request) async {
          expect(request.headers['X-App-Channel'], channel);
          paths.add(request.url.path);
          return http.Response(
            request.url.path == '/chat/teachers' ? '[]' : '{}',
            200,
          );
        }),
      );
      expect(paths, ['/chat/teachers', '/parent/subscription']);
    }
  });
}
