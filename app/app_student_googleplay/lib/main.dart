import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_student/student_app.dart';
import 'package:play_telemetry/play_telemetry.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializePlayTelemetry();
  Api.I.channel = 'googleplay';
  await AppLanguage.I.load();
  await Api.I.loadToken();
  runApp(const StudentApp());
  Telemetry.event(AppEvent.appReady);
}
