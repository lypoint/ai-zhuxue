import 'package:flutter/material.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../models/bubble.dart';

/// 单条聊天气泡：用户消息纯文本，助手消息按 Markdown/LaTeX 渲染。
class MessageBubble extends StatelessWidget {
  final Bubble bubble;
  final VoidCallback onLongPress;
  final VoidCallback? onRetry;
  final bool isLoading;
  const MessageBubble({
    super.key,
    required this.bubble,
    required this.onLongPress,
    this.onRetry,
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
              onLongPress: bubble.text.isEmpty || bubble.failed
                  ? null
                  : onLongPress,
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
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 40),
                  child: Stack(
                    children: [
                      Padding(
                        padding: EdgeInsets.only(
                          top:
                              !isUser &&
                                  bubble.text.isNotEmpty &&
                                  !bubble.failed
                              ? 40
                              : 0,
                          bottom:
                              isUser && bubble.text.isNotEmpty && !bubble.failed
                              ? 40
                              : 0,
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
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
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
                      if (bubble.text.isNotEmpty && !bubble.failed)
                        Positioned(
                          top: isUser ? null : 0,
                          bottom: isUser ? 0 : null,
                          right: 0,
                          child: IconButton(
                            tooltip: '消息操作',
                            icon: const Icon(Icons.more_horiz, size: 20),
                            color: isUser ? Colors.white : Colors.black54,
                            constraints: const BoxConstraints(
                              minWidth: 40,
                              minHeight: 40,
                            ),
                            onPressed: onLongPress,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
            if (onRetry != null)
              TextButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('重试回复'),
              ),
          ],
        ),
      ),
    );
  }
}
