import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:overseas_compliance/overseas_compliance.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await GdprConsentManager.I.resetForTest();
  });

  test('default state requires consent and analytics is not granted', () async {
    final manager = GdprConsentManager.I;
    expect(await manager.isConsentRequired(), isTrue);
    expect(manager.isAnalyticsGranted, isFalse);
  });

  test('granting analytics persists state properly', () async {
    final manager = GdprConsentManager.I;
    await manager.saveConsent(grantAnalytics: true);

    expect(await manager.isConsentRequired(), isFalse);
    expect(manager.isAnalyticsGranted, isTrue);

    // Re-initialize manager to simulate app restart
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool('compliance_gdpr_decided'), isTrue);
    expect(prefs.getBool('compliance_gdpr_analytics_granted'), isTrue);
  });

  test('selecting essential only denies analytics while fulfilling consent requirement', () async {
    final manager = GdprConsentManager.I;
    await manager.saveConsent(grantAnalytics: false);

    expect(await manager.isConsentRequired(), isFalse);
    expect(manager.isAnalyticsGranted, isFalse);
  });

  test('revoking consent turns off analytics', () async {
    final manager = GdprConsentManager.I;
    await manager.saveConsent(grantAnalytics: true);
    expect(manager.isAnalyticsGranted, isTrue);

    await manager.revokeConsent();
    expect(manager.isAnalyticsGranted, isFalse);
    expect(await manager.isConsentRequired(), isFalse);
  });
}
