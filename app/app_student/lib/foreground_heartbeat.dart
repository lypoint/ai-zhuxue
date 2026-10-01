import 'dart:async';

/// 只累计聊天页处于前台的秒数；切到后台时结算不足一分钟的部分。
class ForegroundHeartbeat {
  ForegroundHeartbeat(this.report);

  final void Function(int seconds) report;
  Timer? _timer;
  int _seconds = 0;

  void start() {
    _timer ??= Timer.periodic(const Duration(seconds: 1), (_) {
      _seconds++;
      if (_seconds >= 60) _flush();
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _flush();
  }

  void _flush() {
    if (_seconds == 0) return;
    report(_seconds);
    _seconds = 0;
  }
}
