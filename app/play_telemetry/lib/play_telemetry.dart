import 'package:flutter/foundation.dart';
import 'package:app_core/app_core.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

/// Imported by Google Play shells only. Native collection starts disabled.
Future<void> initializePlayTelemetry({bool initialAnalyticsConsent = false}) async {
  try {
    await _configure(initialAnalyticsConsent);
  } catch (_) {
    // Diagnostics must not prevent login or learning when unavailable.
    Telemetry.events = null;
    Telemetry.errors = null;
    debugPrint("Firebase telemetry initialization unavailable");
  }
}

/// Dynamically updates Firebase Analytics consent state according to user choice.
Future<void> updatePlayTelemetryConsent({required bool analyticsGranted}) async {
  try {
    final analytics = FirebaseAnalytics.instance;
    await analytics.setConsent(
      adStorageConsentGranted: false,
      analyticsStorageConsentGranted: analyticsGranted,
      adUserDataConsentGranted: false,
      adPersonalizationSignalsConsentGranted: false,
    );
    await analytics.setAnalyticsCollectionEnabled(kReleaseMode && analyticsGranted);
  } catch (_) {
    debugPrint("Firebase setConsent update unavailable");
  }
}

Future<void> _configure(bool initialAnalyticsConsent) async {
  await Firebase.initializeApp();
  final analytics = FirebaseAnalytics.instance;
  final crashlytics = FirebaseCrashlytics.instance;
  await analytics.setConsent(
    adStorageConsentGranted: false,
    analyticsStorageConsentGranted: initialAnalyticsConsent,
    adUserDataConsentGranted: false,
    adPersonalizationSignalsConsentGranted: false,
  );
  await analytics.setAnalyticsCollectionEnabled(kReleaseMode && initialAnalyticsConsent);
  await crashlytics.setCrashlyticsCollectionEnabled(kReleaseMode);
  if (!kReleaseMode) return;
  Telemetry.events = (event, result, status) => analytics.logEvent(
    name: switch (event) {
      AppEvent.appReady => 'app_ready',
      AppEvent.login => 'account_login',
      AppEvent.bindStudent => 'student_bind',
      AppEvent.chatSend => 'chat_send',
      AppEvent.createBindCode => 'bind_code_create',
      AppEvent.purchaseVerify => 'purchase_verify',
      AppEvent.restorePurchases => 'purchase_restore',
      AppEvent.logout => 'account_logout',
    },
    parameters: {'result': result.name, if (status != null) 'status': status},
  );
  Telemetry.errors = (type, stack, fatal) =>
      crashlytics.recordError(type, stack, fatal: fatal, printDetails: false);
  final previous = FlutterError.onError;
  FlutterError.onError = (details) {
    previous?.call(details);
    Telemetry.error(
      details.exception,
      details.stack ?? StackTrace.current,
      fatal: true,
    );
  };
  final previousPlatform = PlatformDispatcher.instance.onError;
  PlatformDispatcher.instance.onError = (error, stack) {
    Telemetry.error(error, stack, fatal: true);
    return previousPlatform?.call(error, stack) ?? true;
  };
}
