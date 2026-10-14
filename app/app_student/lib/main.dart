import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'student_app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppLanguage.I.load();
  await Api.I.loadToken();
  runApp(const StudentApp());
}
