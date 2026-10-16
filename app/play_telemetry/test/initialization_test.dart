import 'package:app_core/app_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:play_telemetry/play_telemetry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'unavailable native Firebase leaves the app usable without collection',
    () async {
      await initializePlayTelemetry();
      expect(Telemetry.events, isNull);
      expect(Telemetry.errors, isNull);
      Telemetry.event(AppEvent.appReady);
    },
  );
}
