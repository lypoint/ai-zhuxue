import 'package:flutter/material.dart';
import 'core/api.dart';
import 'features/parent/parent_app.dart';
import 'features/student/student_app.dart';

/// 双端同一代码库：--dart-define=ROLE=student（默认）或 ROLE=parent
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Api.I.loadToken();
  const role = String.fromEnvironment('ROLE', defaultValue: 'student');
  runApp(role == 'parent' ? const ParentApp() : const StudentApp());
}
