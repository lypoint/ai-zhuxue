import 'package:app_student/foreground_heartbeat.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('后台时间不累计，前台零散秒数会结算', (tester) async {
    final reports = <int>[];
    final heartbeat = ForegroundHeartbeat(reports.add);

    heartbeat.start();
    await tester.pump(const Duration(seconds: 30));
    heartbeat.stop();
    expect(reports, [30]);

    await tester.pump(const Duration(seconds: 90));
    expect(reports, [30]);

    heartbeat.start();
    await tester.pump(const Duration(seconds: 60));
    expect(reports, [30, 60]);
    heartbeat.stop();
  });
}
