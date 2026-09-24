import 'package:flutter/material.dart';

/// 未读角标：红底白字圆形计数。
class NotificationBadge extends StatelessWidget {
  final int count;
  const NotificationBadge({super.key, required this.count});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
      constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
      child: Text(
        '$count',
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.white, fontSize: 9),
      ),
    );
  }
}
