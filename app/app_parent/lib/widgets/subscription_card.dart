import 'package:flutter/material.dart';

/// 订阅状态卡（P0 商业闭环）：试用/生效/到期 + 续费按钮。
class SubscriptionCard extends StatelessWidget {
  final Map<String, dynamic> sub;
  final VoidCallback onPay;
  final VoidCallback? onAddSeat;
  final bool billingPending;
  final VoidCallback? onManage;
  const SubscriptionCard({
    super.key,
    required this.sub,
    required this.onPay,
    this.onAddSeat,
    this.billingPending = false,
    this.onManage,
  });

  @override
  Widget build(BuildContext context) {
    final active = sub['active'] == true;
    final trial = sub['plan'] == 'free_trial';
    final canPurchase =
        sub['can_purchase_subscription'] as bool? ?? (!active || trial);
    final hasPending = sub['has_pending_payment'] == true;
    final days = sub['days_left'] as num? ?? 0;
    final freeTeacherCount = sub['free_teacher_count'] as num? ?? 0;
    return Card(
      color: active ? const Color(0xFFE8F5F1) : const Color(0xFFFDEDEC),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: active
                      ? const Color(0xFFD0E9DF)
                      : const Color(0xFFF8D8D3),
                  child: Icon(
                    active
                        ? Icons.workspace_premium_outlined
                        : Icons.warning_amber_rounded,
                    color: active
                        ? const Color(0xFF246C60)
                        : const Color(0xFFAB3E32),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        active
                            ? (trial
                                  ? '免费试用中 · 剩余 $days 天'
                                  : '订阅生效中 · 剩余 $days 天')
                            : (freeTeacherCount > 0
                                  ? '订阅已到期 · 部分老师设有免费额度'
                                  : '订阅已到期'),
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '孩子名额 ${sub['used_seats'] ?? 0}/${sub['seat_count'] ?? 1} · ${active
                            ? '到期后请查看老师免费额度'
                            : freeTeacherCount > 0
                            ? '孩子可按各老师额度使用'
                            : '续费后孩子即可继续学习'}',
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.6,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (!active && freeTeacherCount > 0)
                        Text(
                          '$freeTeacherCount 位老师设有每日免费回复，每个学生单独计次',
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF8B5C1C),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              onManage == null
                  ? '家庭月订阅 ¥${sub['monthly_price_cny'] ?? 66}/月 · 不累加有效期'
                  : '家庭月订阅 · 价格与扣款周期见商店确认页面',
            ),
            if (active && !trial)
              Text(
                onManage == null
                    ? '当前订阅仍有效，可升级名额档位，到期后再续订。'
                    : '当前订阅仍有效，可立即升级名额或管理自动续订。',
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 140),
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(0, 48),
                    ),
                    onPressed: billingPending || (!canPurchase && !hasPending)
                        ? null
                        : onPay,
                    child: Text(
                      billingPending
                          ? '处理中…'
                          : hasPending
                          ? '继续支付'
                          : !canPurchase
                          ? '订阅有效'
                          : trial
                          ? '开通月订阅'
                          : '立即续订',
                    ),
                  ),
                ),
                if (onManage != null)
                  TextButton(
                    onPressed: billingPending ? null : onManage,
                    child: const Text('恢复购买 / 管理订阅'),
                  ),
                if (onAddSeat != null)
                  TextButton(
                    onPressed: billingPending ? null : onAddSeat,
                    child: const Text('增加名额'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
