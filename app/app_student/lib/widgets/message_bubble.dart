import 'package:flutter/material.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../models/bubble.dart';

/// 单条聊天气泡：用户消息纯文本，助手消息按 Markdown/LaTeX 渲染。长按触发菜单。
class MessageBubble extends StatelessWidget {
  final Bubble bubble;
  final VoidCallback onLongPress;
  const MessageBubble({
    super.key,
    required this.bubble,
    required this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = bubble.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onLongPress: onLongPress,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.75,
          ),
          decoration: BoxDecoration(
            color: isUser
                ? Theme.of(context).colorScheme.primary
                : Colors.white,
            borderRadius: BorderRadius.circular(18),
            border: isUser
                ? null
                : Border.all(
                    color: Theme.of(
                      context,
                    ).colorScheme.outlineVariant.withValues(alpha: .6),
                  ),
            boxShadow: isUser
                ? null
                : const [
                    BoxShadow(
                      color: Color(0x0A1C2940),
                      blurRadius: 10,
                      offset: Offset(0, 3),
                    ),
                  ],
          ),
          child: isUser
              ? Text(bubble.text, style: const TextStyle(color: Colors.white))
              : GptMarkdown(
                  bubble.text,
                  style: const TextStyle(color: Colors.black87, height: 1.4),
                  useDollarSignsForLatex: true,
                ),
        ),
      ),
    );
  }
}
