import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/billing.dart';
import 'payment_screen.dart';

class WechatBilling extends ParentBilling {
  @override
  String get channel => 'wechat';
  @override
  Future<bool?> purchase(BuildContext context, String kind) async {
    final pending = await Api.I.pendingPayments();
    final items = pending['items'] as List<dynamic>;
    int? targetSeats;
    if (items.isEmpty && kind == 'seat_add') {
      final current = await Api.I.subscription();
      final seats = (current['seat_count'] as num).toInt();
      final catalog = await Api.I.billingCatalog(seatCount: seats + 1);
      if (!context.mounted) return false;
      final tiers = (catalog['items'] as List<dynamic>)
          .where((tier) => (tier['seat_count'] as num) > seats)
          .toList();
      targetSeats = await showDialog<int>(
        context: context,
        builder: (context) => SimpleDialog(
          title: Text(tr("选择升级后的总名额")),
          children: [
            for (final tier in tiers)
              SimpleDialogOption(
                onPressed: () =>
                    Navigator.pop(context, tier['seat_count'] as int),
                child: Text(
                  tr("{0} 个名额 · ¥{1}/月", [
                    tier['seat_count'],
                    ((tier['amount_cents'] as num) / 100).toStringAsFixed(2),
                  ]),
                ),
              ),
          ],
        ),
      );
      if (targetSeats == null || !context.mounted) return false;
    }
    final order = items.isNotEmpty
        ? Map<String, dynamic>.from(items.first as Map)
        : await Api.I.createPaymentOrder(
            kind,
            'parent-${DateTime.now().microsecondsSinceEpoch}',
            targetSeatCount: targetSeats,
          );
    if (!context.mounted) return false;
    return Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => PaymentScreen(order: order)),
    );
  }
}
