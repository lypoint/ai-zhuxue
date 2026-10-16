import 'package:app_core/app_core.dart';
import 'package:app_parent/parent_app.dart';
import 'package:app_parent/screens/login_screen.dart';
import 'package:app_parent_googleplay/google_login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
  });
  setUp(() {
    SharedPreferences.setMockInitialValues({'token': 'old-phone-session'});
    Api.I.channel = 'googleplay';
    Api.I.clearToken();
  });
  tearDown(() {
    Api.I.channel = '';
    Api.I.clearToken();
    Api.onUnauthorized = null;
  });

  testWidgets(
    'Google channel ignores old phone session and returns to its login gate',
    (tester) async {
      await Api.I.loadToken();
      expect(Api.I.hasToken, isFalse);
      await tester.pumpWidget(
        ParentApp(
          loginBuilder: (_) =>
              GoogleLoginScreen(authenticate: () async => null),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(GoogleLoginScreen), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      expect(find.byType(PhoneLoginScreen), findsNothing);
      expect(find.byType(PasswordLoginButton), findsOneWidget);
      // A return-to-login route must resolve the same channel page.
      final context = tester.element(find.byType(GoogleLoginScreen));
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
      await tester.pumpAndSettle();
      expect(find.byType(GoogleLoginScreen), findsOneWidget);
      expect(find.byType(PhoneLoginScreen), findsNothing);
    },
  );

  testWidgets(
    'cancelling Google account selection keeps the login page usable',
    (tester) async {
      int attempts = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: GoogleLoginScreen(
            authenticate: () async {
              attempts++;
              return null;
            },
          ),
        ),
      );
      await tester.tap(find.byType(OutlinedButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(OutlinedButton));
      await tester.pumpAndSettle();
      expect(attempts, 2);
      expect(Api.I.hasToken, isFalse);
    },
  );
}
