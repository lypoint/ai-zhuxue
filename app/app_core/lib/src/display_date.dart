/// Compact local time; server timestamps without a zone are UTC.
String displayDate(Object? value, {bool dateOnly = false}) {
  final raw = value?.toString() ?? '';
  if (raw.isEmpty) return '—';
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return '—';
  final date = raw.length <= 10
      ? parsed
      : (RegExp(r'(Z|[+-]\d{2}:?\d{2})$').hasMatch(raw)
                ? parsed
                : DateTime.parse('${raw}Z'))
            .toLocal();
  String pad(int n) => n.toString().padLeft(2, '0');
  final day = '${date.year}-${pad(date.month)}-${pad(date.day)}';
  return dateOnly || raw.length <= 10
      ? day
      : '$day ${pad(date.hour)}:${pad(date.minute)}';
}
