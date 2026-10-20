/// 聊天气泡数据：区分用户/助手，携带 messageId 以支持收藏。
class Bubble {
  final String role;
  final String text;
  final int? messageId;
  final bool failed;
  final List<dynamic> contentBlocks;
  final Map<String, dynamic>? imageJob;
  Bubble(
    this.role,
    this.text, {
    this.messageId,
    this.failed = false,
    this.contentBlocks = const [],
    this.imageJob,
  });
}
