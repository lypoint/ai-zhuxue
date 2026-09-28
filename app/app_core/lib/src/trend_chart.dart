import 'package:flutter/material.dart';

/// 成绩趋势折线图：不同满分制已由服务端统一换算为百分比再比较（规格 7.2）。
class TrendChart extends StatelessWidget {
  final List<Map<String, dynamic>> points;
  final double height;

  const TrendChart({super.key, required this.points, this.height = 170});

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return SizedBox(
        height: height,
        child: const Center(
          child: Text(
            '暂无趋势数据',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ),
      );
    }
    return SizedBox(
      height: height,
      width: double.infinity,
      child: CustomPaint(
        painter: _TrendPainter(
          points: points,
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }
}

class _TrendPainter extends CustomPainter {
  static const _padLeft = 40.0;
  static const _padRight = 16.0;
  static const _padTop = 18.0;
  static const _padBottom = 24.0;

  final List<Map<String, dynamic>> points;
  final Color color;
  _TrendPainter({required this.points, required this.color});

  double _x(int i, int n, double plotW) =>
      _padLeft + (n <= 1 ? plotW / 2 : plotW * i / (n - 1));

  double _y(num percentage, double plotH) {
    final p = percentage.toDouble().clamp(0.0, 100.0);
    return _padTop + plotH * (1 - p / 100);
  }

  void _text(
    Canvas canvas,
    String label,
    Offset pos, {
    TextStyle style = const TextStyle(fontSize: 10, color: Colors.grey),
    TextAlign align = TextAlign.center,
  }) {
    final tp = TextPainter(
      text: TextSpan(text: label, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    final dx = switch (align) {
      TextAlign.left => pos.dx,
      TextAlign.right => pos.dx - tp.width,
      _ => pos.dx - tp.width / 2,
    };
    tp.paint(canvas, Offset(dx, pos.dy));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final plotW = size.width - _padLeft - _padRight;
    final plotH = size.height - _padTop - _padBottom;
    final values = points
        .map((p) => ((p['percentage'] as num?) ?? 0).toDouble())
        .toList();
    final n = values.length;

    // 网格与百分比刻度
    final grid = Paint()
      ..color = Colors.grey.withValues(alpha: .22)
      ..strokeWidth = 1;
    for (final v in const [0, 50, 100]) {
      final y = _padTop + plotH * (1 - v / 100);
      canvas.drawLine(
        Offset(_padLeft, y),
        Offset(size.width - _padRight, y),
        grid,
      );
      _text(canvas, '$v%', Offset(0, y - 6), align: TextAlign.left);
    }

    // 折线
    if (n >= 2) {
      final line = Paint()
        ..color = color
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round;
      final path = Path()..moveTo(_x(0, n, plotW), _y(values[0], plotH));
      for (var i = 1; i < n; i++) {
        path.lineTo(_x(i, n, plotW), _y(values[i], plotH));
      }
      canvas.drawPath(path, line);
    }

    // 数据点与百分比标注（点多于 10 个时只标注首尾，避免重叠）
    final dot = Paint()..color = color;
    final ring = Paint()
      ..color = Colors.white
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    for (var i = 0; i < n; i++) {
      final c = Offset(_x(i, n, plotW), _y(values[i], plotH));
      canvas.drawCircle(c, 4, dot);
      canvas.drawCircle(c, 5.5, ring);
      if (n <= 10 || i == 0 || i == n - 1) {
        _text(
          canvas,
          _fmt(values[i]),
          Offset(c.dx, c.dy - 21),
          style: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            color: Color(0xFF172334),
          ),
        );
      }
    }

    // 日期轴：首、中、尾
    String date(int i) => points[i]['exam_date'] as String? ?? '';
    _text(
      canvas,
      _shortDate(date(0)),
      Offset(_padLeft, size.height - _padBottom + 6),
      align: TextAlign.left,
    );
    if (n >= 3) {
      _text(
        canvas,
        _shortDate(date(n ~/ 2)),
        Offset(_x(n ~/ 2, n, plotW), size.height - _padBottom + 6),
      );
    }
    if (n >= 2) {
      _text(
        canvas,
        _shortDate(date(n - 1)),
        Offset(size.width - _padRight, size.height - _padBottom + 6),
        align: TextAlign.right,
      );
    }
  }

  String _fmt(num v) => v % 1 == 0 ? '${v.toInt()}' : v.toStringAsFixed(1);
  String _shortDate(String d) => d.length >= 10 ? d.substring(5, 10) : d;

  @override
  bool shouldRepaint(_TrendPainter old) =>
      old.points != points || old.color != color;
}
