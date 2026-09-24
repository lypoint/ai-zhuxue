/// 聊天气泡数据：区分用户/助手，携带 messageId 以支持收藏。
class Bubble {
  final String role;
  final String text;
  final int? messageId;
  Bubble(this.role, this.text, {this.messageId});
}
