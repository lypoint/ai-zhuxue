import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

class FamilyTime {
  static String? zone;
  static Duration fallbackOffset = const Duration(hours: 8);
  static void configure(Map<String, dynamic> data) {
    zone = data['timezone'] as String?;
    fallbackOffset = Duration(
      minutes: ((data['legacy_timezone_offset_hours'] as num? ?? 8) * 60)
          .round(),
    );
  }

  static DateTime get today {
    final now = local(DateTime.now());
    return DateTime.utc(now.year, now.month, now.day);
  }

  static bool _initialized = false;
  static List<String> get zones {
    if (!_initialized) {
      tzdata.initializeTimeZones();
      _initialized = true;
    }
    return tz.timeZoneDatabase.locations.keys.toList()..sort();
  }

  static DateTime local(DateTime value) {
    zones;
    final name = zone;
    return name == null
        ? value.toUtc().add(fallbackOffset)
        : tz.TZDateTime.from(value, tz.getLocation(name));
  }
}

/// Compact local time; server timestamps without a zone are UTC.
String displayDate(Object? value, {bool dateOnly = false}) {
  final raw = value?.toString() ?? '';
  if (raw.isEmpty) return '—';
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return '—';
  final date = raw.length <= 10
      ? parsed
      : FamilyTime.local(
          RegExp(r'(Z|[+-]\d{2}:?\d{2})$').hasMatch(raw)
              ? parsed
              : DateTime.parse('${raw}Z'),
        );
  String pad(int n) => n.toString().padLeft(2, '0');
  final day = '${date.year}-${pad(date.month)}-${pad(date.day)}';
  return dateOnly || raw.length <= 10
      ? day
      : '$day ${pad(date.hour)}:${pad(date.minute)}';
}
