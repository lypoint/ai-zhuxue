import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:app_student/screens/image_crop_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Uint8List source;

  setUp(() async {
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    canvas.drawRect(
      const Rect.fromLTWH(0, 0, 100, 100),
      Paint()..color = Colors.red,
    );
    canvas.drawRect(
      const Rect.fromLTWH(100, 0, 100, 100),
      Paint()..color = Colors.blue,
    );
    final picture = recorder.endRecording();
    final image = await picture.toImage(200, 100);
    source = (await image.toByteData(
      format: ui.ImageByteFormat.png,
    ))!.buffer.asUint8List();
    image.dispose();
    picture.dispose();
  });

  Future<void> open(
    WidgetTester tester,
    void Function(Uint8List?) onResult,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                onResult(
                  await Navigator.of(context).push<Uint8List>(
                    MaterialPageRoute(
                      builder: (_) => ImageCropScreen(bytes: source),
                    ),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pumpAndSettle();
  }

  testWidgets('cancel returns no image', (tester) async {
    Uint8List? result;
    var returned = false;
    await open(tester, (value) {
      result = value;
      returned = true;
    });
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    expect(returned, isTrue);
    expect(result, isNull);
  });

  for (final moveSelection in [false, true]) {
    testWidgets('crop exports selected pixels; move=$moveSelection', (
      tester,
    ) async {
      Uint8List? result;
      await open(tester, (value) => result = value);
      final bounds = tester.getRect(find.byType(RawImage));
      final gesture = await tester.startGesture(bounds.topLeft);
      await gesture.moveBy(const Offset(1, 0));
      await gesture.moveTo(bounds.topLeft + Offset(bounds.width / 2, 0));
      await gesture.up();
      await tester.pump();
      if (moveSelection) {
        final center =
            bounds.topLeft + Offset(bounds.width * .75, bounds.height / 2);
        await tester.dragFrom(center, Offset(-bounds.width, 0));
        await tester.pump();
      }
      await tester.tap(find.widgetWithText(TextButton, '完成'));
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      });
      await tester.pumpAndSettle();
      expect(result, isNotNull);
      await tester.runAsync(() async {
        final codec = await ui.instantiateImageCodec(result!);
        final image = (await codec.getNextFrame()).image;
        expect(image.width, closeTo(100, 2));
        expect(image.height, 100);
        final pixels = (await image.toByteData())!;
        final center = (50 * image.width + image.width ~/ 2) * 4;
        expect(pixels.getUint8(center + 2), moveSelection ? 54 : 243);
        expect(pixels.getUint8(center), moveSelection ? 244 : 33);
        image.dispose();
        codec.dispose();
      });
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('unchanged selection preserves original bytes', (tester) async {
    Uint8List? result;
    await open(tester, (value) => result = value);
    await tester.tap(find.widgetWithText(TextButton, '完成'));
    await tester.pumpAndSettle();
    expect(result, source);
  });

  testWidgets('invalid image keeps confirm disabled and allows cancel', (
    tester,
  ) async {
    source = Uint8List.fromList([0, 1, 2]);
    await open(tester, (_) {});
    expect(find.text('无法读取图片，请检查相机或相册权限'), findsOneWidget);
    expect(
      tester
          .widget<TextButton>(find.widgetWithText(TextButton, '完成'))
          .onPressed,
      isNull,
    );
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    expect(find.byType(ImageCropScreen), findsNothing);
  });
}
