import 'package:app_core/app_core.dart';
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
    AppLanguage.watch(context);
    final active = sub['active'] == true;
    final trial = sub['plan'] == 'free_trial';
    if (sub['plan'] == 'permanent' && active) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                tr('永久会员'),
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              Text(
                tr('孩子名额 {0}/{1}', [
                  sub['used_seats'] ?? 0,
                  sub['seat_count'] ?? 100,
                ]),
              ),
            ],
          ),
        ),
      );
    }

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
                                  ? tr("免费试用中 · 剩余 {0} 天", [days])
                                  : tr("订阅生效中 · 剩余 {0} 天", [days]))
                            : (freeTeacherCount > 0
                                  ? tr("订阅已到期 · 部分老师设有免费额度")
                                  : tr("订阅已到期")),
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        tr("孩子名额 {0}/{1} · {2}", [
                          sub['used_seats'] ?? 0,
                          sub['seat_count'] ?? 1,
                          active
                              ? tr("到期后请查看老师免费额度")
                              : freeTeacherCount > 0
                              ? tr("孩子可按各老师额度使用")
                              : tr("续费后孩子即可继续学习"),
                        ]),
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.6,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (!active && freeTeacherCount > 0)
                        Text(
                          tr("{0} 位老师设有每日免费回复，每个学生单独计次", [freeTeacherCount]),
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
            if (sub['teachers'] is List &&
                (sub['teachers'] as List).isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: (sub['teachers'] as List)
                    .map(
                      (teacher) => Chip(label: Text(teacher['name'] as String)),
                    )
                    .toList(),
              ),
            ],
            const SizedBox(height: 16),
            Text(
              onManage == null
                  ? tr("家庭月订阅 ¥{0}/月 · 到期手动续订", [
                      (sub['monthly_price_cny'] as num? ?? 66).toStringAsFixed(
                        2,
                      ),
                    ])
                  : tr("家庭月订阅 · 价格与扣款周期见商店确认页面"),
            ),
            if (sub['expires_at'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  tr("有效期至 {0}", [
                    displayDate(sub['expires_at'], dateOnly: true),
                  ]),
                ),
              ),
            if (active && !trial)
              Text(
                onManage == null
                    ? tr("当前订阅仍有效，可升级名额档位，到期后再续订。")
                    : tr("当前订阅仍有效，可立即升级名额或管理自动续订。"),
              ),
            if (trial) Text(tr("立即付款，剩余试用时长保留。")),
            if (onManage != null)
              Text(tr("赠送时长不推迟自动扣款；取消自动续订后仍可使用。")),
            if (!trial && onManage != null) ...[
              Text(tr("下次扣款")),
              Text(sub['auto_renew'] == true
                  ? sub['next_billing_at'] != null
                      ? displayDate(sub['next_billing_at'])
                      : tr("扣款日期以支付平台为准。")
                  : tr("不会自动扣款")),
            ],
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
                          ? tr("处理中…")
                          : hasPending
                          ? tr("继续支付")
                          : !canPurchase
                          ? tr("订阅有效")
                          : trial
                          ? tr("开通月订阅")
                          : tr("立即续订"),
                    ),
                  ),
                ),
                if (onManage != null)
                  TextButton(
                    onPressed: billingPending ? null : onManage,
                    child: Text(tr("恢复购买 / 管理订阅")),
                  ),
                if (onAddSeat != null)
                  TextButton(
                    onPressed: billingPending ? null : onAddSeat,
                    child: Text(tr("增加名额")),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
