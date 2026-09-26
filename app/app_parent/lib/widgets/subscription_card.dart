import 'package:flutter/material.dart';

/// 订阅状态卡（P0 商业闭环）：试用/生效/到期 + 续费按钮。
class SubscriptionCard extends StatelessWidget {
  final Map<String, dynamic> sub;
  final VoidCallback onPay;
  final VoidCallback? onAddSeat;
  const SubscriptionCard({
    super.key,
    required this.sub,
    required this.onPay,
    this.onAddSeat,
  });

  @override
  Widget build(BuildContext context) {
    final active = sub['active'] == true;
    final trial = sub['plan'] == 'free_trial';
    final days = sub['days_left'] as num? ?? 0;
    final postTrialFree = sub['post_trial_daily_free_count'] as num? ?? 0;
    return Card(
      color: active ? const Color(0xFFE8F5F1) : const Color(0xFFFDEDEC),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(
              active ? Icons.verified : Icons.warning_amber_rounded,
              color: active ? const Color(0xFF15857A) : Colors.red,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    active
                        ? (trial ? '免费试用中 · 剩余 $days 天' : '订阅生效中 · 剩余 $days 天')
                        : (postTrialFree > 0 ? '订阅已到期 · 部分老师仍可免费使用' : '订阅已到期'),
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  Text(
                    '孩子名额 ${sub['used_seats'] ?? 0}/${sub['seat_count'] ?? 1} · ${active ? '到期后孩子将无法继续使用' : postTrialFree > 0 ? '符合条件的老师可继续使用' : '续费后孩子即可继续学习'}',
                    style: const TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                  if (!active && postTrialFree > 0)
                    Text(
                      '开启免费权益的老师可每天免费 $postTrialFree 次',
                      style: const TextStyle(fontSize: 12, color: Colors.orange),
                    ),
                ],
              ),
            ),
            // 防御性约束：个别环境（模拟器 gfxstream）CJK 字形测量异常会使按钮
            // 占满整行、把 Expanded 文本列压成 40px；封顶宽度在正常设备上无视觉差异。
            Column(
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 140),
                  child: FilledButton(
                    onPressed: onPay,
                    child: Text(active ? '续费' : '立即开通'),
                  ),
                ),
                if (onAddSeat != null)
                  TextButton(onPressed: onAddSeat, child: const Text('增加名额')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
