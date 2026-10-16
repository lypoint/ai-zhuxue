import 'dart:async';

/// Fixed vocabulary prevents business data from entering analytics or crash logs.
enum AppEvent {
  appReady,
  login,
  bindStudent,
  chatSend,
  createBindCode,
  purchaseVerify,
  restorePurchases,
  logout,
}

enum EventResult { success, failure }

typedef EventSink =
    Future<void> Function(AppEvent event, EventResult result, int? status);
typedef ErrorSink =
    Future<void> Function(String type, StackTrace stack, bool fatal);

class Telemetry {
  static EventSink? events;
  static ErrorSink? errors;

  static void event(
    AppEvent event, {
    EventResult result = EventResult.success,
    int? status,
  }) {
    final sink = events;
    if (sink != null) unawaited(_ignore(() => sink(event, result, status)));
  }

  static void error(Object error, StackTrace stack, {bool fatal = false}) {
    final sink = errors;
    if (sink == null) return;
    final type = error.runtimeType.toString().replaceAll(
      RegExp(r'[^a-zA-Z0-9_]'),
      '_',
    );
    // Keep code locations only; exception messages and arbitrary stack text may contain user data.
    final frames = stack
        .toString()
        .split('\n')
        .where(
          (line) => RegExp(
            r'^#\d+\s+[a-zA-Z0-9_.$<> ]+ \(package:[a-zA-Z0-9_./-]+:\d+:\d+\)$',
          ).hasMatch(line),
        )
        .take(80)
        .join('\n');
    unawaited(_ignore(() => sink(type, StackTrace.fromString(frames), fatal)));
  }

  static Future<void> _ignore(Future<void> Function() action) async {
    try {
      await action();
    } catch (_) {
      /* Telemetry must never break the app. */
    }
  }
}
