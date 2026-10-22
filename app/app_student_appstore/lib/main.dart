import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_student/student_app.dart';
import 'package:app_tracking_transparency/app_tracking_transparency.dart';
import 'package:overseas_compliance/overseas_compliance.dart';

Future<void> _requestTrackingAuthorization() async {
  try {
    final status = await AppTrackingTransparency.trackingAuthorizationStatus;
    if (status == TrackingStatus.notDetermined) {
      await AppTrackingTransparency.requestTrackingAuthorization();
    }
  } catch (_) {
    // Non-fatal fallback for simulator or non-iOS environments
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppLanguage.I.load();
  Api.I.channel = 'appstore';
  await Api.I.loadToken();
  final navigatorKey = GlobalKey<NavigatorState>();
  runApp(
    OverseasComplianceWrapper(
      navigatorKey: navigatorKey,
      onPostConsent: _requestTrackingAuthorization,
      child: StudentApp(navigatorKey: navigatorKey),
    ),
  );
}
