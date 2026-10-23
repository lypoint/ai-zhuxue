import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Crop in decoded image coordinates so the preview and exported pixels agree.
class ImageCropScreen extends StatefulWidget {
  const ImageCropScreen({super.key, required this.bytes});

  final Uint8List bytes;

  @override
  State<ImageCropScreen> createState() => _ImageCropScreenState();
}

class _ImageCropScreenState extends State<ImageCropScreen> {
  ui.Image? _image;
  Rect _crop = const Rect.fromLTWH(0, 0, 1, 1);
  bool _failed = false;
  bool _saving = false;
  int? _corner;
  late Rect _startCrop;
  late Offset _startPointer;

  @override
  void initState() {
    super.initState();
    _decode();
  }

  Future<void> _decode() async {
    try {
      final codec = await ui.instantiateImageCodec(widget.bytes);
      late ui.Image image;
      try {
        image = (await codec.getNextFrame()).image;
      } finally {
        codec.dispose();
      }
      if (!mounted) {
        image.dispose();
        return;
      }
      setState(() => _image = image);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void dispose() {
    _image?.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (_crop == const Rect.fromLTWH(0, 0, 1, 1)) {
      Navigator.pop(context, widget.bytes);
      return;
    }
    final image = _image!;
    setState(() => _saving = true);
    try {
      final left = (_crop.left * image.width).floor();
      final top = (_crop.top * image.height).floor();
      final right = (_crop.right * image.width).ceil().clamp(
        left + 1,
        image.width,
      );
      final bottom = (_crop.bottom * image.height).ceil().clamp(
        top + 1,
        image.height,
      );
      final source = Rect.fromLTRB(
        left.toDouble(),
        top.toDouble(),
        right.toDouble(),
        bottom.toDouble(),
      );
      final recorder = ui.PictureRecorder();
      Canvas(
        recorder,
      ).drawImageRect(image, source, Offset.zero & source.size, Paint());
      final picture = recorder.endRecording();
      try {
        final cropped = await picture.toImage(right - left, bottom - top);
        try {
          final data = await cropped.toByteData(format: ui.ImageByteFormat.png);
          if (data == null) throw StateError('Image encoding failed');
          if (mounted) Navigator.pop(context, data.buffer.asUint8List());
        } finally {
          cropped.dispose();
        }
      } finally {
        picture.dispose();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr('裁切失败，请重试'))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _editor(ui.Image image) => LayoutBuilder(
    builder: (context, constraints) {
      // Leave room for the touch targets even when the selection fills the image.
      final scale = math.min(
        math.max(1, constraints.maxWidth - 48) / image.width,
        math.max(1, constraints.maxHeight - 48) / image.height,
      );
      final size = Size(image.width * scale, image.height * scale);
      final bounds = Alignment.center.inscribe(
        size,
        Offset.zero & constraints.biggest,
      );
      final selection = Rect.fromLTRB(
        bounds.left + _crop.left * size.width,
        bounds.top + _crop.top * size.height,
        bounds.left + _crop.right * size.width,
        bounds.top + _crop.bottom * size.height,
      );
      final corners = [
        selection.topLeft,
        selection.topRight,
        selection.bottomRight,
        selection.bottomLeft,
      ];
      return GestureDetector(
        key: const ValueKey('crop-editor'),
        behavior: HitTestBehavior.opaque,
        onPanStart: _saving
            ? null
            : (details) {
                _corner = null;
                final point = details.localPosition;
                for (var i = 0; i < corners.length; i++) {
                  if ((point - corners[i]).distance <= 28) {
                    _corner = i;
                    break;
                  }
                }
                if (_corner == null && !selection.contains(point)) return;
                _corner ??= 4;
                _startCrop = _crop;
                _startPointer = point;
              },
        onPanUpdate: _saving
            ? null
            : (details) {
                final corner = _corner;
                if (corner == null) return;
                final delta = details.localPosition - _startPointer;
                final dx = delta.dx / size.width;
                final dy = delta.dy / size.height;
                final start = _startCrop;
                final minWidth = math.min(1.0, 48 / size.width);
                final minHeight = math.min(1.0, 48 / size.height);
                setState(() {
                  if (corner == 4) {
                    _crop = start.shift(
                      Offset(
                        dx.clamp(-start.left, 1 - start.right),
                        dy.clamp(-start.top, 1 - start.bottom),
                      ),
                    );
                  } else {
                    final moveLeft = corner == 0 || corner == 3;
                    final moveTop = corner == 0 || corner == 1;
                    _crop = Rect.fromLTRB(
                      moveLeft
                          ? (start.left + dx).clamp(0, start.right - minWidth)
                          : start.left,
                      moveTop
                          ? (start.top + dy).clamp(0, start.bottom - minHeight)
                          : start.top,
                      moveLeft
                          ? start.right
                          : (start.right + dx).clamp(start.left + minWidth, 1),
                      moveTop
                          ? start.bottom
                          : (start.bottom + dy).clamp(start.top + minHeight, 1),
                    );
                  }
                });
              },
        child: Stack(
          children: [
            Positioned.fromRect(
              rect: bounds,
              child: RawImage(image: image),
            ),
            Positioned.fill(
              child: CustomPaint(painter: _CropOverlay(selection)),
            ),
          ],
        ),
      );
    },
  );

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_saving,
    child: Scaffold(
      appBar: AppBar(
        title: Text(tr('裁切图片')),
        leading: IconButton(
          tooltip: tr('取消'),
          icon: const Icon(Icons.close),
          onPressed: _saving ? null : () => Navigator.pop(context),
        ),
        actions: [
          TextButton(
            onPressed: _image == null || _saving ? null : _confirm,
            child: Text(tr('完成')),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(tr('拖动四角调整裁切范围，拖动选区移动位置')),
            ),
            Expanded(
              child: _failed
                  ? Center(child: Text(tr('无法读取图片，请检查相机或相册权限')))
                  : _image == null || _saving
                  ? const Center(child: CircularProgressIndicator())
                  : _editor(_image!),
            ),
          ],
        ),
      ),
    ),
  );
}

class _CropOverlay extends CustomPainter {
  const _CropOverlay(this.selection);
  final Rect selection;

  @override
  void paint(Canvas canvas, Size size) {
    final mask = Path()
      ..fillType = PathFillType.evenOdd
      ..addRect(Offset.zero & size)
      ..addRect(selection);
    canvas.drawPath(mask, Paint()..color = Colors.black54);
    canvas.drawRect(
      selection,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
    for (final point in [
      selection.topLeft,
      selection.topRight,
      selection.bottomRight,
      selection.bottomLeft,
    ]) {
      canvas.drawCircle(point, 8, Paint()..color = Colors.white);
      canvas.drawCircle(
        point,
        8,
        Paint()
          ..color = Colors.black54
          ..style = PaintingStyle.stroke,
      );
    }
  }

  @override
  bool shouldRepaint(_CropOverlay oldDelegate) =>
      selection != oldDelegate.selection;
}
