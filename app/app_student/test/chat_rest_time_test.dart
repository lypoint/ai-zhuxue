import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response response(Object data, [int status = 200]) => http.Response(
  jsonEncode(data),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

http.Response initialResponse(http.Request request) {
  if (request.url.path.endsWith('/teachers')) {
    return response([
      {
        'teacher_id': 1,
        'name': '老师',
        'selected': true,
        'access': 'available',
        'capabilities': {'image_input': true, 'image_output': true},
      },
    ]);
  }
  if (request.url.path.endsWith('/sessions')) return response([]);
  return response(<String, dynamic>{});
}

void main() {
  testWidgets('休息时禁用输入、图片和发送，结束后恢复草稿及发送状态', (tester) async {
    var resting = false;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/availability')) {
        return response({'resting': resting, 'refresh_after_seconds': 1});
      }
      return initialResponse(request);
    });
    await http.runWithClient(() async {
      await tester.pumpWidget(
        MaterialApp(theme: appTheme(Colors.teal), home: const ChatScreen()),
      );
      await tester.pumpAndSettle();
      IconButton send() => tester.widget<IconButton>(
        find.byWidgetPredicate((w) => w is IconButton && w.tooltip == '发送问题'),
      );
      expect(send().onPressed, isNull);
      await tester.enterText(find.byType(TextField), '  ');
      expect(send().onPressed, isNull);
      await tester.enterText(find.byType(TextField), '学习问题');
      await tester.pump();
      expect(send().onPressed, isNotNull);
      resting = true;
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();
      final input = tester.widget<TextField>(find.byType(TextField));
      expect(input.enabled, isFalse);
      expect(input.decoration!.hintText, '休息时间到啦');
      expect(input.controller!.text, '学习问题');
      expect(send().onPressed, isNull);
      final disabledColor = tester
          .widget<Material>(
            find
                .descendant(
                  of: find.byWidget(send()),
                  matching: find.byType(Material),
                )
                .first,
          )
          .color;
      expect(disabledColor, isNotNull);
      expect(
        disabledColor,
        isNot(
          Theme.of(tester.element(find.byType(TextField))).colorScheme.primary,
        ),
      );
      expect(
        tester
            .widget<IconButton>(
              find.byWidgetPredicate(
                (w) => w is IconButton && w.tooltip == '添加题目图片',
              ),
            )
            .onPressed,
        isNull,
      );
      resting = false;
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
      expect(send().onPressed, isNotNull);
      await tester.enterText(find.byType(TextField), '');
      await tester.pump();
      expect(send().onPressed, isNull);
      await tester.pumpWidget(const SizedBox());
    }, () => client);
    client.close();
  });

  testWidgets('发送撞上休息边界时保留草稿，只显示休息提示', (tester) async {
    var sends = 0;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/availability')) {
        return response({'resting': false});
      }
      if (request.url.path.endsWith('/chat/stream')) {
        sends++;
        return response({'detail': '现在是休息时间（22:00-6:00），明天再学吧'}, 423);
      }
      return initialResponse(request);
    });
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '我的题目');
      await tester.pump();
      await tester.tap(
        find.byWidgetPredicate((w) => w is IconButton && w.tooltip == '发送问题'),
      );
      await tester.pumpAndSettle();
      expect(sends, 1);
      final input = tester.widget<TextField>(find.byType(TextField));
      expect(input.enabled, isFalse);
      expect(input.controller!.text, '我的题目');
      expect(input.decoration!.hintText, '休息时间到啦');
      expect(find.text('现在是休息时间（22:00-6:00），明天再学吧'), findsOneWidget);
      expect(find.textContaining('发送失败'), findsNothing);
      expect(find.textContaining('⚠️'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    }, () => client);
    client.close();
  });
  for (final uploadStatus in [200, 503, 423]) {
    testWidgets('图片上传状态 $uploadStatus 决定空输入是否能发送，休息拦截显示休息提示', (tester) async {
      final dir = Directory.systemTemp.createTempSync('chat-rest-test-');
      final image = File('${dir.path}/question.png')
        ..writeAsBytesSync(
          base64Decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==',
          ),
        );
      addTearDown(() => dir.deleteSync(recursive: true));
      const picker = MethodChannel('plugins.flutter.io/image_picker');
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        picker,
        (_) async => image.path,
      );
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          picker,
          null,
        ),
      );
      final upload = Completer<http.Response>();
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/availability')) {
          return response({'resting': false});
        }
        if (request.url.path.endsWith('/media/uploads')) return upload.future;
        if (request.url.host == 'upload.example.com') return response({});
        if (request.url.path.endsWith('/complete')) {
          return response({'type': 'image', 'asset_id': 'asset'});
        }
        return initialResponse(request);
      });
      await http.runWithClient(() async {
        await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
        await tester.pumpAndSettle();
        await tester.tap(find.byTooltip('添加题目图片'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('从相册选择'));
        // The upload is deliberately pending; its progress indicator keeps animating.
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 400));
        IconButton send() => tester.widget<IconButton>(
          find.byWidgetPredicate((w) => w is IconButton && w.tooltip == '发送问题'),
        );
        expect(send().onPressed, isNull);
        upload.complete(
          uploadStatus == 200
              ? response({
                  'max_bytes': 10000,
                  'upload_url': 'https://upload.example.com',
                  'key': 'key',
                  'token': 'test',
                  'asset_id': 'asset',
                })
              : response({
                  'detail': uploadStatus == 423 ? '休息时间到啦' : '上传失败',
                }, uploadStatus),
        );
        // File reads use the real event loop.
        for (var i = 0; i < 10; i++) {
          await tester.runAsync(() async {
            await Future<void>.delayed(const Duration(milliseconds: 20));
          });
          await tester.pump();
        }
        await tester.pumpAndSettle();
        expect(send().onPressed == null, uploadStatus != 200);
        if (uploadStatus == 200) {
          await tester.binding.setSurfaceSize(const Size(320, 640));
          addTearDown(() => tester.binding.setSurfaceSize(null));
          for (var i = 0; i < 2; i++) {
            await tester.tap(find.byTooltip('添加题目图片'));
            await tester.pumpAndSettle();
            await tester.tap(find.text('从相册选择'));
            for (var j = 0; j < 10; j++) {
              await tester.runAsync(() async {
                await Future<void>.delayed(const Duration(milliseconds: 20));
              });
              await tester.pump();
            }
            await tester.pumpAndSettle();
          }
          final composer = find.byKey(const ValueKey('chat-composer'));
          final thumbnails = find.descendant(
            of: composer,
            matching: find.byWidgetPredicate(
              (w) => w is Image && w.image is MemoryImage,
            ),
          );
          expect(thumbnails, findsNWidgets(3));
          final bounds = tester.getRect(composer);
          for (var i = 0; i < 3; i++) {
            final thumbnail = tester.getRect(thumbnails.at(i));
            expect(bounds.contains(thumbnail.topLeft), isTrue);
            expect(bounds.contains(thumbnail.bottomRight), isTrue);
            expect(
              thumbnail.bottom,
              lessThan(tester.getTopLeft(find.byType(TextField)).dy),
            );
          }
          expect(tester.takeException(), isNull);
        }
        if (uploadStatus == 423) {
          expect(
            tester.widget<TextField>(find.byType(TextField)).enabled,
            isFalse,
          );
          expect(find.text('重试上传'), findsNothing);
          expect(find.textContaining('上传失败'), findsNothing);
        }
        await tester.pumpWidget(const SizedBox());
      }, () => client);
      client.close();
    });
  }
}
