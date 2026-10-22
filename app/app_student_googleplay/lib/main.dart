import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_student/student_app.dart';
import 'package:overseas_compliance/overseas_compliance.dart';
import 'package:play_telemetry/play_telemetry.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final consentManager = GdprConsentManager.I;
  await consentManager.init();
  await initializePlayTelemetry(
    initialAnalyticsConsent: consentManager.isAnalyticsGranted,
  );
  GdprConsentManager.onConsentChanged = (granted) async {
    await updatePlayTelemetryConsent(analyticsGranted: granted);
  };
  Api.I.channel = 'googleplay';
  await AppLanguage.I.load();
  await Api.I.loadToken();
  final navigatorKey = GlobalKey<NavigatorState>();
  runApp(
    OverseasComplianceWrapper(
      navigatorKey: navigatorKey,
      onConsentDecision: (granted) {
        updatePlayTelemetryConsent(analyticsGranted: granted);
      },
      child: StudentApp(
        navigatorKey: navigatorKey,
        extraAccountActionBuilder: (context) => [
          const GdprPrivacySettingsTile(),
        ],
      ),
    ),
  );
  Telemetry.event(AppEvent.appReady);
}
