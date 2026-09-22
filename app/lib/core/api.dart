import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

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
    String deviceId,
    String nickname,
  ) async {
    final data = await _send(
      'POST',
      '/auth/student/login',
      body: {
        'bind_code': bindCode,
        'device_id': deviceId,
        'nickname': nickname,
      },
    );
    await _saveToken(data['token'] as String);
    return data['role'] as String;
  }

  Future<Map<String, dynamic>> familyOverview() =>
      _send('GET', '/parent/family');
  Future<Map<String, dynamic>> createBindCode() => _send('POST', '/bind/code');
  Future<List<dynamic>> conversations(int studentId) async =>
      (await _send('GET', '/parent/students/$studentId/conversations'))
          as List<dynamic>;
  Future<List<dynamic>> messages(int conversationId) async =>
      (await _send('GET', '/parent/conversations/$conversationId/messages'))
          as List<dynamic>;
  Future<List<dynamic>> fenceEvents(int conversationId) async =>
      (await _send('GET', '/parent/conversations/$conversationId/fence-events'))
          as List<dynamic>;
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
  Future<Map<String, dynamic>> paySubscription() =>
      _send('POST', '/parent/subscription/pay');

  // ---------- 通知中心（P0） ----------
  Future<Map<String, dynamic>> notifications({bool unreadOnly = false}) =>
      _send(
        'GET',
        '/parent/notifications${unreadOnly ? '?unread_only=true' : ''}',
      );
  Future<void> readAllNotifications() =>
      _send('POST', '/parent/notifications/read-all');

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
  Future<Map<String, dynamic>> sendChat(int? conversationId, String content) =>
      _send(
        'POST',
        '/chat',
        body: {'conversation_id': conversationId, 'content': content},
      );

  /// 流式聊天（SSE）。onDelta 逐段回调增量文本；meta 事件先回调 onMeta；
  /// 返回 done 事件数据（message_id/tokens）。流内 error 事件抛 ApiException(503)。
  Future<Map<String, dynamic>> sendChatStream(
    int? conversationId,
    String content, {
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
