import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// 后端地址：Android 模拟器用 10.0.2.2 访问宿主机。
/// 覆盖方式：flutter run --dart-define=API_BASE=http://192.168.x.x:8100
const apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://10.0.2.2:8100',
);

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

class Api {
  static final Api I = Api._();
  Api._();
  String? _token;

  Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('token');
  }

  Future<void> _saveToken(String? t) async {
    _token = t;
    final prefs = await SharedPreferences.getInstance();
    if (t == null) {
      await prefs.remove('token');
    } else {
      await prefs.setString('token', t);
    }
  }

  bool get hasToken => _token != null;
  void clearToken() {
    _token = null;
  }

  Future<dynamic> _sendRaw(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$apiBase$path');
    final headers = {
      'Content-Type': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };
    final resp = switch (method) {
      'POST' => await http.post(
        uri,
        headers: headers,
        body: jsonEncode(body ?? {}),
      ),
      'PUT' => await http.put(
        uri,
        headers: headers,
        body: jsonEncode(body ?? {}),
      ),
      'PATCH' => await http.patch(
        uri,
        headers: headers,
        body: jsonEncode(body ?? {}),
      ),
      'DELETE' => await http.delete(uri, headers: headers),
      _ => await http.get(uri, headers: headers),
    };
    final data = jsonDecode(utf8.decode(resp.bodyBytes));
    if (resp.statusCode >= 400) {
      throw ApiException(
        resp.statusCode,
        (data['detail'] ?? '请求失败').toString(),
      );
    }
    return data;
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async =>
      (await _sendRaw(method, path, body: body)) as Map<String, dynamic>;

  Future<String> registerGuardian(
    String phone,
    String smsCode,
    String nickname,
    String realName,
    String idNumber,
  ) async {
    final data = await _send(
      'POST',
      '/auth/guardian/register',
      body: {
        'phone': phone,
        'sms_code': smsCode,
        'nickname': nickname,
        'real_name': realName,
        'id_number': idNumber,
      },
    );
    await _saveToken(data['token'] as String);
    return data['role'] as String;
  }

  Future<String> studentLogin(
    String bindCode,
    String installationId,
    String nickname,
  ) async {
    final data = await _send(
      'POST',
      '/auth/student/login',
      body: {
        'bind_code': bindCode,
        'installation_id': installationId,
        'device_id': installationId,
        'nickname': nickname,
      },
    );
    await _saveToken(data['token'] as String);
    return data['role'] as String;
  }

  Future<Map<String, dynamic>> familyOverview() =>
      _send('GET', '/parent/family');
  Future<Map<String, dynamic>> students() => _send('GET', '/parent/students');

  Future<Map<String, dynamic>> createStudent(
    String nickname, {
    String gradeBand = '8-12',
  }) => _send(
    'POST',
    '/parent/students',
    body: {'nickname': nickname, 'grade_band': gradeBand},
  );
  Future<Map<String, dynamic>> createBindCode({
    String purpose = 'new_student',
    int? targetStudentId,
  }) => _send(
    'POST',
    '/bind/code',
    body: {
      'purpose': purpose,
      if (targetStudentId != null) 'target_student_id': targetStudentId,
    },
  );

  Future<Map<String, dynamic>> rebindCode(int studentId) =>
      createBindCode(purpose: 'rebind', targetStudentId: studentId);
  Future<List<dynamic>> studentDevices(int studentId) async =>
      (await _sendRaw('GET', '/parent/students/$studentId/devices'))
          as List<dynamic>;
  Future<void> revokeStudentDevice(int studentId, int deviceId) => _send(
        'POST',
        '/parent/students/$studentId/devices/$deviceId/revoke',
      );
  Future<List<dynamic>> conversations(int studentId, {String? status}) async {
    final suffix = status == null
        ? ''
        : '?status=${Uri.encodeQueryComponent(status)}';
    return (await _sendRaw(
          'GET',
          '/parent/students/$studentId/conversations$suffix',
        ))
        as List<dynamic>;
  }

  Future<List<dynamic>> messages(int conversationId) async =>
      (await _sendRaw('GET', '/parent/conversations/$conversationId/messages'))
          as List<dynamic>;
  Future<List<dynamic>> fenceEvents(int conversationId) async =>
      (await _sendRaw(
            'GET',
            '/parent/conversations/$conversationId/fence-events',
          ))
          as List<dynamic>;
  Future<Map<String, dynamic>> submitFenceFeedback(
    int conversationId, {
    int? messageId,
    int? eventId,
    String note = '',
  }) => _send(
    'POST',
    '/parent/conversations/$conversationId/feedback',
    body: {
      if (messageId != null) 'message_id': messageId,
      if (eventId != null) 'event_id': eventId,
      if (note.trim().isNotEmpty) 'note': note.trim(),
    },
  );
  Future<void> updateSettings(
    int dailyCap,
    bool reviewEnabled, {
    bool quietEnabled = true,
    int quietStart = 22,
    int quietEnd = 6,
    int dailyMinutesCap = 60,
    bool notifyFence = true,
  }) => _send(
    'PUT',
    '/parent/settings',
    body: {
      'daily_message_cap': dailyCap,
      'review_enabled': reviewEnabled,
      'quiet_enabled': quietEnabled,
      'quiet_start': quietStart,
      'quiet_end': quietEnd,
      'daily_minutes_cap': dailyMinutesCap,
      'notify_fence': notifyFence,
    },
  );

  /// 学习摘要（家长首页）：{today:{questions,blocked,guided,study,minutes}, week:{...,active_days}}
  Future<Map<String, dynamic>> studentSummary(int studentId) =>
      _send('GET', '/parent/students/$studentId/summary');

  Future<List<dynamic>> chatHistory(int conversationId) async =>
      (await _send(
            'GET',
            '/chat/conversations?conversation_id=$conversationId',
          ))
          as List<dynamic>;

  /// 学生端恢复最近对话：{conversation_id: int|null, messages: [...]}
  Future<Map<String, dynamic>> latestConversation() =>
      _send('GET', '/chat/latest');

  /// 学生端会话列表（Codex 风格抽屉）：[{conversation_id,title,message_count,last_time}]
  Future<List<dynamic>> sessions() async =>
      (await _sendRaw('GET', '/chat/sessions')) as List<dynamic>;

  /// 加载指定会话全部消息（[{id,role,content,fence_action,created_at}]）
  Future<List<dynamic>> conversationMessages(int conversationId) async =>
      (await _sendRaw(
            'GET',
            '/chat/conversations?conversation_id=$conversationId',
          ))
          as List<dynamic>;

  /// 重命名会话（学生端抽屉长按）
  Future<void> renameSession(int conversationId, String title) =>
      _send('PATCH', '/chat/sessions/$conversationId', body: {'title': title});

  /// 删除会话（学生端抽屉长按，连同消息与围栏流水）
  Future<void> deleteSession(int conversationId) =>
      _send('DELETE', '/chat/sessions/$conversationId');

  /// 置顶/取消置顶会话
  Future<void> pinSession(int conversationId, bool pinned) => _send(
    'PUT',
    '/chat/sessions/$conversationId/pin',
    body: {'pinned': pinned},
  );

  /// 家长端用量与成本估算：{total:{tokens_in,tokens_out,cost}, today:{...}, unit}
  Future<Map<String, dynamic>> studentUsage(int studentId) =>
      _send('GET', '/parent/students/$studentId/usage');

  // ---------- 学段（P2 分龄） ----------
  Future<void> setGradeBand(int studentId, String band) => _send(
    'PUT',
    '/parent/students/$studentId/grade-band',
    body: {'grade_band': band},
  );

  /// 修改孩子昵称（P2 遗漏补齐）
  Future<void> setStudentNickname(int studentId, String nickname) => _send(
    'PUT',
    '/parent/students/$studentId/nickname',
    body: {'nickname': nickname},
  );

  /// 孩子收藏（学习沉淀，家长可见）
  Future<List<dynamic>> studentFavorites(int studentId) async =>
      (await _sendRaw('GET', '/parent/students/$studentId/favorites'))
          as List<dynamic>;

  /// 审查内容搜索（标题+消息全文）
  Future<List<dynamic>> searchConversations(int studentId, String query) async {
    final path = Uri(
      path: '/parent/students/$studentId/search',
      queryParameters: {'q': query},
    ).toString();
    return (await _sendRaw('GET', path)) as List<dynamic>;
  }

  /// 我的学习统计（学生自己可见）：{today:{questions,blocked,minutes}, week:{...,active_days}, favorites}
  Future<Map<String, dynamic>> myStats() => _send('GET', '/chat/my-stats');

  /// 端侧活跃心跳（每 60s，聊天页活跃时上报；防刷单次≤120）
  Future<void> heartbeat(int seconds) =>
      _send('POST', '/chat/heartbeat', body: {'seconds': seconds});

  // ---------- 收藏（P2 学生端） ----------
  Future<Map<String, dynamic>> addFavorite(int messageId) =>
      _send('POST', '/chat/favorites', body: {'message_id': messageId});
  Future<List<dynamic>> myFavorites() async =>
      (await _sendRaw('GET', '/chat/favorites')) as List<dynamic>;
  Future<void> deleteFavorite(int id) => _send('DELETE', '/chat/favorites/$id');

  // ---------- 订阅（P0） ----------
  Future<Map<String, dynamic>> subscription() =>
      _send('GET', '/parent/subscription');
  Future<Map<String, dynamic>> paySubscription({String? idempotencyKey}) =>
      _send(
        'POST',
        '/parent/subscription/pay',
        body: {if (idempotencyKey != null) 'idempotency_key': idempotencyKey},
      );
  Future<Map<String, dynamic>> addSubscriptionSeats(
    int count, {
    required String idempotencyKey,
  }) => _send(
    'POST',
    '/parent/subscription/seats',
    body: {'count': count, 'idempotency_key': idempotencyKey},
  );

  // ---------- 通知中心（P0） ----------
  Future<Map<String, dynamic>> notifications({bool unreadOnly = false}) =>
      _send(
        'GET',
        '/parent/notifications${unreadOnly ? '?unread_only=true' : ''}',
      );
  Future<void> readAllNotifications() =>
      _send('POST', '/parent/notifications/read-all');

  Future<String> installationId() async {
    const secure = FlutterSecureStorage();
    try {
      final existing = await secure.read(key: 'installation_id');
      if (existing != null && existing.length >= 8) return existing;
      final value = _newInstallationId();
      await secure.write(key: 'installation_id', value: value);
      return value;
    } catch (_) {
      // Test/web fallback; mobile builds use Keychain/Keystore above.
    }
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString('installation_id');
    if (existing != null && existing.length >= 8) return existing;
    final value = _newInstallationId();
    await prefs.setString('installation_id', value);
    return value;
  }

  String _newInstallationId() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  Future<List<dynamic>> teachers() async =>
      (await _sendRaw('GET', '/chat/teachers')) as List<dynamic>;

  Future<List<dynamic>> studentGrades({bool includeDeleted = false}) async {
    final suffix = includeDeleted ? '?include_deleted=true' : '';
    return (await _sendRaw('GET', '/chat/grades$suffix')) as List<dynamic>;
  }

  Future<Map<String, dynamic>> addStudentGrade(Map<String, dynamic> grade) =>
      _send('POST', '/chat/grades', body: grade);
  Future<Map<String, dynamic>> editStudentGrade(
    int gradeId,
    Map<String, dynamic> grade,
  ) => _send('PATCH', '/chat/grades/$gradeId', body: grade);
  Future<void> deleteStudentGrade(int gradeId) =>
      _send('DELETE', '/chat/grades/$gradeId');
  Future<void> restoreStudentGrade(int gradeId) =>
      _send('POST', '/chat/grades/$gradeId/restore');
  Future<List<dynamic>> studentGradeHistory(int gradeId) async =>
      (await _sendRaw('GET', '/chat/grades/$gradeId/history')) as List<dynamic>;
  Future<Map<String, dynamic>> studentGradeTrend({String? subject, String? from, String? to}) async {
    final query = <String, String>{
      if (subject != null && subject.isNotEmpty) 'subject': subject,
      if (from != null && from.isNotEmpty) 'from': from,
      if (to != null && to.isNotEmpty) 'to': to,
    };
    final suffix = query.isEmpty
        ? ''
        : '?${query.entries.map((e) => '${Uri.encodeQueryComponent(e.key)}=${Uri.encodeQueryComponent(e.value)}').join('&')}';
    return _send('GET', '/chat/grade-trend$suffix');
  }

  Future<Map<String, dynamic>> studentAcademicAssessment({
    String? from,
    String? to,
  }) => _send(
    'POST',
    '/chat/academic-assessments',
    body: {if (from != null) 'from': from, if (to != null) 'to': to},
  );
  Future<List<dynamic>> studentAcademicAssessments() async =>
      (await _sendRaw('GET', '/chat/academic-assessments')) as List<dynamic>;

  Future<List<dynamic>> parentGrades(
    int studentId, {
    bool includeDeleted = false,
  }) async {
    final suffix = includeDeleted ? '?include_deleted=true' : '';
    return (await _sendRaw('GET', '/parent/students/$studentId/grades$suffix'))
        as List<dynamic>;
  }

  Future<Map<String, dynamic>> addParentGrade(
    int studentId,
    Map<String, dynamic> grade,
  ) => _send('POST', '/parent/students/$studentId/grades', body: grade);
  Future<Map<String, dynamic>> editParentGrade(
    int studentId,
    int gradeId,
    Map<String, dynamic> grade,
  ) => _send(
    'PATCH',
    '/parent/students/$studentId/grades/$gradeId',
    body: grade,
  );
  Future<void> deleteParentGrade(int studentId, int gradeId) =>
      _send('DELETE', '/parent/students/$studentId/grades/$gradeId');
  Future<void> restoreParentGrade(int studentId, int gradeId) =>
      _send('POST', '/parent/students/$studentId/grades/$gradeId/restore');
  Future<List<dynamic>> parentGradeHistory(int studentId, int gradeId) async =>
      (await _sendRaw(
            'GET',
            '/parent/students/$studentId/grades/$gradeId/history',
          ))
          as List<dynamic>;
  Future<Map<String, dynamic>> parentGradeTrend(
    int studentId, {
    String? subject,
    String? from,
    String? to,
  }) async {
    final query = <String, String>{
      if (subject != null && subject.isNotEmpty) 'subject': subject,
      if (from != null && from.isNotEmpty) 'from': from,
      if (to != null && to.isNotEmpty) 'to': to,
    };
    final suffix = query.isEmpty
        ? ''
        : '?${query.entries.map((e) => '${Uri.encodeQueryComponent(e.key)}=${Uri.encodeQueryComponent(e.value)}').join('&')}';
    return _send('GET', '/parent/students/$studentId/grade-trend$suffix');
  }

  Future<Map<String, dynamic>> parentAcademicAssessment(int studentId) => _send(
    'POST',
    '/parent/students/$studentId/academic-assessments',
    body: {},
  );
  Future<List<dynamic>> parentAcademicAssessments(int studentId) async =>
      (await _sendRaw(
            'GET',
            '/parent/students/$studentId/academic-assessments',
          ))
          as List<dynamic>;
  Future<Map<String, dynamic>> parentWellbeingAssessment(int studentId) =>
      _send(
        'POST',
        '/parent/students/$studentId/wellbeing-assessments',
        body: {},
      );
  Future<List<dynamic>> parentWellbeingAssessments(int studentId) async =>
      (await _sendRaw(
            'GET',
            '/parent/students/$studentId/wellbeing-assessments',
          ))
          as List<dynamic>;
  Future<void> ackWellbeingAssessment(int assessmentId, String status) => _send(
    'POST',
    '/parent/wellbeing-assessments/$assessmentId/ack',
    body: {'status': status},
  );

  /// 退出登录：服务端吊销当前 token（版本+1），并清除本地
  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } on ApiException {
      // token 已失效等场景不阻塞本地登出
    }
    await _saveToken(null);
  }

  /// 发消息（非流式）：返回 assistant 消息。fence 429/423 等业务码由 ApiException 抛出。
  Future<Map<String, dynamic>> sendChat(
    int? conversationId,
    String content, {
    int? teacherId,
  }) => _send(
    'POST',
    '/chat',
    body: {
      'conversation_id': conversationId,
      'content': content,
      if (teacherId != null) 'teacher_id': teacherId,
    },
  );

  /// 流式聊天（SSE）。onDelta 逐段回调增量文本；meta 事件先回调 onMeta；
  /// 返回 done 事件数据（message_id/tokens）。流内 error 事件抛 ApiException(503)。
  Future<Map<String, dynamic>> sendChatStream(
    int? conversationId,
    String content, {
    int? teacherId,
    void Function(String text)? onDelta,
    void Function(Map<String, dynamic> meta)? onMeta,
  }) async {
    final client = http.Client();
    try {
      final req = http.Request('POST', Uri.parse('$apiBase/chat/stream'))
        ..headers['Content-Type'] = 'application/json'
        ..headers['Authorization'] = 'Bearer ${_token ?? ''}'
        ..body = jsonEncode({
          'conversation_id': conversationId,
          'content': content,
          if (teacherId != null) 'teacher_id': teacherId,
        });
      final resp = await client.send(req);
      if (resp.statusCode >= 400) {
        final body = await resp.stream.bytesToString();
        final data = jsonDecode(body);
        throw ApiException(
          resp.statusCode,
          (data['detail'] ?? '请求失败').toString(),
        );
      }
      Map<String, dynamic>? done;
      String? event;
      String? dataBuf;
      Future<void> dispatch() async {
        if (event == null || dataBuf == null) return;
        final data = jsonDecode(dataBuf!) as Map<String, dynamic>;
        switch (event) {
          case 'meta':
            conversationIdCache = data['conversation_id'] as int?;
            onMeta?.call(data);
          case 'delta':
            onDelta?.call(data['text'] as String);
          case 'done':
            done = data;
          case 'error':
            throw ApiException(503, data['message'] as String? ?? '服务不可用');
        }
        event = null;
        dataBuf = null;
      }

      await for (final raw
          in resp.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (raw.startsWith('event:')) {
          await dispatch();
          event = raw.substring(6).trim();
        } else if (raw.startsWith('data:')) {
          dataBuf = raw.substring(5).trim();
        } else if (raw.trim().isEmpty) {
          await dispatch();
        }
      }
      await dispatch();
      return done ?? {};
    } finally {
      client.close();
    }
  }

  int? conversationIdCache;
}
