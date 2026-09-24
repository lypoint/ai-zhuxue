import 'package:flutter_test/flutter_test.dart';
import 'package:app_core/app_core.dart';

void main() {
  test('ApiException 暴露状态码与消息', () {
    final e = ApiException(423, '休息时间到啦');
    expect(e.status, 423);
    expect(e.toString(), '休息时间到啦');
  });
}
