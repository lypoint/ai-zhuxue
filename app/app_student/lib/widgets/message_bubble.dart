import 'package:flutter/material.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../models/bubble.dart';

/// 单条聊天气泡：用户消息纯文本，助手消息按 Markdown/LaTeX 渲染。
class MessageBubble extends StatelessWidget {
  final Bubble bubble;
  final VoidCallback onLongPress;
  final VoidCallback onCopy;
  final bool isLoading;
  const MessageBubble({
    super.key,
    required this.bubble,
    required this.onLongPress,
    required this.onCopy,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = bubble.role == 'user';
    return Padding(
      // 参考聊天页：消息列表两侧 12，老师卡片再左缩 4、右留 40。
      padding: EdgeInsets.only(left: isUser ? 12 : 16, right: isUser ? 12 : 52),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: isUser
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            GestureDetector(
              onLongPress: onLongPress,
              child: Container(
                margin: const EdgeInsets.only(top: 4),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                width: isUser ? null : double.infinity,
                constraints: isUser
                    ? const BoxConstraints(maxWidth: 267.5)
                    : null,
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
                    ? Text(
                        bubble.text,
                        style: const TextStyle(color: Colors.white),
                      )
                    : isLoading
                    ? const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          SizedBox(width: 8),
                          Text('正在回答…'),
                        ],
                      )
                    : GptMarkdown(
                        bubble.text,
                        style: const TextStyle(
                          color: Colors.black87,
                          height: 1.4,
                        ),
                        useDollarSignsForLatex: true,
                      ),
              ),
            ),
            if (bubble.text.isNotEmpty)
              TextButton.icon(
                onPressed: onCopy,
                icon: const Icon(Icons.copy_outlined, size: 16),
                label: const Text('复制'),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 28),
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  visualDensity: VisualDensity.compact,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
