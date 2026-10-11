import 'package:flutter/material.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../models/bubble.dart';

/// 用户消息纯文本，老师讲解保留 Markdown、公式与学习反馈。
class MessageBubble extends StatelessWidget {
  final Bubble bubble;
  final VoidCallback onLongPress;
  final VoidCallback? onRetry;
  final bool isLoading;
  final void Function(String)? onFeedback;
  final String? feedback;
  const MessageBubble({
    super.key,
    required this.bubble,
    required this.onLongPress,
    this.onRetry,
    this.isLoading = false,
    this.onFeedback,
    this.feedback,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = bubble.role == 'user';
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: Column(
          crossAxisAlignment: isUser
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            GestureDetector(
              onLongPress: isUser || bubble.text.isEmpty || bubble.failed
                  ? null
                  : onLongPress,
              child: Container(
                constraints: isUser
                    ? BoxConstraints(
                        maxWidth: MediaQuery.sizeOf(context).width * .8,
                      )
                    : null,
                width: isUser ? null : double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: isUser ? scheme.primary : Colors.white,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(22),
                    topRight: const Radius.circular(22),
                    bottomLeft: Radius.circular(isUser ? 22 : 6),
                    bottomRight: Radius.circular(isUser ? 6 : 22),
                  ),
                  border: isUser
                      ? null
                      : Border.all(color: const Color(0xFFE3EBE6)),
                ),
                child: isUser
                    ? Text(
                        bubble.text,
                        style: TextStyle(color: scheme.onPrimary, height: 1.5),
                      )
                    : isLoading
                    ? const Row(
                        children: [
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          SizedBox(width: 10),
                          Text('正在回答…'),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (bubble.text.isNotEmpty && !bubble.failed)
                            Row(
                              children: [
                                Icon(
                                  Icons.auto_awesome_outlined,
                                  size: 16,
                                  color: scheme.primary,
                                ),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    '老师讲解',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: scheme.onSurfaceVariant,
                                    ),
                                  ),
                                ),
                                IconButton(
                                  tooltip: '消息操作',
                                  icon: const Icon(Icons.more_horiz, size: 20),
                                  onPressed: onLongPress,
                                ),
                              ],
                            ),
                          GptMarkdown(
                            bubble.text,
                            style: TextStyle(
                              color: scheme.onSurface,
                              height: 1.6,
                            ),
                            useDollarSignsForLatex: true,
                          ),
                          if (!bubble.failed && bubble.messageId != null) ...[
                            const SizedBox(height: 12),
                            const Divider(),
                            const SizedBox(height: 4),
                            Wrap(
                              spacing: 4,
                              children: [
                                for (final entry in const {
                                  'understood': '懂了',
                                  'not_understood': '不懂',
                                  'continue': '继续讲解',
                                }.entries)
                                  TextButton(
                                    onPressed:
                                        onFeedback == null ||
                                            feedback == entry.key
                                        ? null
                                        : () => onFeedback!(entry.key),
                                    child: Text(
                                      '${feedback == entry.key ? '✓ ' : ''}${entry.value}',
                                    ),
                                  ),
                              ],
                            ),
                          ],
                        ],
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
