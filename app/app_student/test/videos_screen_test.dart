import 'dart:convert';
import 'package:app_student/screens/videos_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('搜索编码关键词，翻页保留原查询，失败后可以重试', (tester) async {
    final queries = <Map<String, String>>[];
    var fail = false;
    final client = MockClient((request) async {
      queries.add(request.url.queryParameters);
      return http.Response(
        jsonEncode(
          fail
              ? {'detail': '平台暂不可用'}
              : {
                  'items': [
                    {
                      'id': 'BV1CiYe6HEBV',
                      'title': '一元二次方程课程',
                      'author': '老师',
                      'duration': '16:33',
                    },
                  ],
                  'page': int.parse(request.url.queryParameters['page']!),
                  'has_more': true,
                },
        ),
        fail ? 503 : 200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: VideosScreen()));
      await tester.enterText(find.byType(TextField), '一元二次方程 & 数学');
      await tester.tap(find.text('搜索'));
      await tester.pumpAndSettle();
      expect(find.text('一元二次方程课程'), findsOneWidget);
      expect(queries.last['q'], '一元二次方程 & 数学');
      await tester.enterText(find.byType(TextField), '尚未提交的新关键词');
      await tester.tap(find.text('下一页'));
      await tester.pumpAndSettle();
      expect(queries.last, {'q': '一元二次方程 & 数学', 'page': '2'});
      fail = true;
      await tester.tap(find.text('搜索'));
      await tester.pumpAndSettle();
      expect(find.text('平台暂不可用'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('搜索'));
      await tester.pumpAndSettle();
      expect(find.text('一元二次方程课程'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }, () => client);
  });
}
