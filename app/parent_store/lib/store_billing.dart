import 'dart:async';

import 'package:app_core/app_core.dart';
import 'package:app_parent/billing.dart';
import 'package:flutter/material.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';
import 'package:url_launcher/url_launcher.dart';

export 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';

abstract class StoreAdapter {
  String get channel;
  InAppPurchasePlatform get platform;
  String reference(PurchaseDetails purchase);
  bool monthly(ProductDetails product);
  Future<PurchaseParam> parameters(
    ProductDetails product,
    Map<String, dynamic> intent,
  );
  Uri get managementUrl;
}

/// One listener lives for the app lifetime, including purchases restored at startup.
class StoreBilling extends ParentBilling with WidgetsBindingObserver {
  StoreBilling(this.adapter) {
    WidgetsBinding.instance.addObserver(this);
    _listener = adapter.platform.purchaseStream.listen(
      _receive,
      onError: (_) {
        message = '商店连接失败，请重新恢复购买';
        notifyListeners();
      },
    );
  }
  final StoreAdapter adapter;
  late final StreamSubscription<List<PurchaseDetails>> _listener;
  final Map<String, PurchaseDetails> _unfinished = {};
  Future<void> _queue = Future.value();
  String? message;
  bool busy = false;
  bool awaitingPurchase = false;
  bool get canBuy => !busy && !awaitingPurchase && _unfinished.isEmpty;
  int verifiedCount = 0;
  @override
  int get revision => verifiedCount;
  @override
  String get channel => adapter.channel;

  void _receive(List<PurchaseDetails> purchases) {
    for (final purchase in purchases) {
      if (purchase.status == PurchaseStatus.pending) {
        awaitingPurchase = true;
        message = '购买待确认，商店确认后将自动核对权益';
      } else if (purchase.status == PurchaseStatus.error ||
          purchase.status == PurchaseStatus.canceled) {
        awaitingPurchase = false;
        message = purchase.status == PurchaseStatus.canceled
            ? '已取消购买'
            : '购买未完成，请重试';
      } else {
        awaitingPurchase = false;
        try {
          final reference = adapter.reference(purchase);
          if (reference.isEmpty) throw StateError('missing purchase reference');
          _unfinished[reference] = purchase;
        } catch (_) {
          message = '商店交易凭据不完整，请恢复购买重试';
        }
      }
    }
    notifyListeners();
    retry();
  }

  Future<void> retry() {
    _queue = _queue.then((_) async {
      if (!Api.I.hasToken) return;
      for (final entry in _unfinished.entries.toList()) {
        try {
          await Api.I.verifyStorePurchase(channel, entry.key);
          if (entry.value.pendingCompletePurchase) {
            await adapter.platform.completePurchase(entry.value);
          }
          _unfinished.remove(entry.key);
          verifiedCount++;
          message = '已核对商店订阅，家庭权益已更新';
        } on ApiException catch (error) {
          message = error.message;
        } catch (_) {
          message = '验单暂未完成，请点击恢复购买重试';
        }
        notifyListeners();
      }
    });
    return _queue;
  }

  @override
  Future<void> recover() async {
    try {
      await restore();
    } catch (_) {
      message = '暂时无法恢复订阅，可在订阅管理页重试';
      notifyListeners();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && Api.I.hasToken) {
      unawaited(recover());
    }
  }

  bool _restoring = false;
  Future<void> restore() async {
    if (_restoring) return;
    _restoring = true;
    try {
      final account = await Api.I.billingAccount();
      await retry();
      await adapter.platform.restorePurchases(
        applicationUserName: account['account_token'] as String,
      );
      message = '已请求恢复购买，核对结果后将更新权益';
      notifyListeners();
    } finally {
      _restoring = false;
    }
  }

  Future<void> buy(ProductDetails product, String code) async {
    if (!canBuy) return;
    busy = true;
    message = null;
    notifyListeners();
    try {
      final intent = await Api.I.prepareStorePurchase(channel, code);
      if (intent['product_id'] != product.id) {
        throw StateError('商店商品配置已变更，请刷新页面');
      }
      final param = await adapter.parameters(product, intent);
      awaitingPurchase = true;
      if (!await adapter.platform.buyNonConsumable(purchaseParam: param)) {
        throw StateError('未能启动商店支付，请重试');
      }
    } catch (_) {
      awaitingPurchase = false;
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  @override
  Future<bool?> purchase(BuildContext context, String kind) async {
    final before = verifiedCount;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => StoreSubscriptionScreen(billing: this, kind: kind),
      ),
    );
    return verifiedCount > before;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_listener.cancel());
    super.dispose();
  }
}

class StoreSubscriptionScreen extends StatefulWidget {
  const StoreSubscriptionScreen({
    super.key,
    required this.billing,
    required this.kind,
  });
  final StoreBilling billing;
  final String kind;
  @override
  State<StoreSubscriptionScreen> createState() =>
      _StoreSubscriptionScreenState();
}

class _StoreSubscriptionScreenState extends State<StoreSubscriptionScreen> {
  List<(Map<String, dynamic>, ProductDetails)>? _items;
  String? _error;
  bool _working = false;
  @override
  void initState() {
    super.initState();
    widget.billing.addListener(_changed);
    _load();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    widget.billing.removeListener(_changed);
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final billing = widget.billing;
      if (!await billing.adapter.platform.isAvailable()) {
        throw StateError('当前设备无法连接商店');
      }
      // Recover transactions before deciding whether a new purchase is allowed.
      await billing.restore();
      final current = await Api.I.subscription();
      final seats = (current['seat_count'] as num).toInt();
      final catalog = await Api.I.billingCatalog(
        seatCount: seats,
        channel: billing.channel,
      );
      final tiers = (catalog['items'] as List).cast<Map<String, dynamic>>();
      if (tiers.isEmpty) {
        if (mounted) setState(() => _items = []);
        return;
      }
      final response = await billing.adapter.platform.queryProductDetails(
        tiers.map((t) => t['product_id'] as String).toSet(),
      );
      if (response.error != null) throw StateError('商店商品加载失败，请稍后重试');
      final items = <(Map<String, dynamic>, ProductDetails)>[];
      for (final tier in tiers) {
        final target = tier['seat_count'] as int;
        if (widget.kind == 'seat_add' && target <= seats) continue;
        if (current['active'] == true &&
            current['plan'] != 'free_trial' &&
            target <= seats) {
          continue;
        }
        final matches = response.productDetails
            .where(
              (p) => p.id == tier['product_id'] && billing.adapter.monthly(p),
            )
            .toList();
        if (matches.length == 1) {
          final product = matches.single;
          if (product.currencyCode == 'CNY' &&
              (product.rawPrice * 100).round() != tier['amount_cents']) {
            throw StateError('商店月价与统一价格不一致，请联系客服');
          }
          items.add((tier, product));
        }
      }
      if (mounted) {
        setState(() {
          _items = items;
          _error = null;
        });
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is StateError
              ? error.message.toString()
              : '暂时无法加载订阅，请重试',
        );
      }
    }
  }

  Future<void> _action(Future<void> Function() action) async {
    setState(() => _working = true);
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is StateError
              ? error.message.toString()
              : '操作未完成，请稍后重试',
        );
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final billing = widget.billing;
    final disabled = _working || billing.busy;
    return Scaffold(
      appBar: AppBar(title: const Text('家庭月订阅')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Text('订阅按月自动续订，名额升级在商店确认并完成验单后立即生效。升级扣款、旧订阅结算和续订时间以商店确认页面为准。'),
          const SizedBox(height: 16),
          if (_error != null) Text(_error!),
          if (billing.message != null) Text(billing.message!),
          if (_items == null && _error == null)
            const Center(child: CircularProgressIndicator()),
          for (final (tier, product)
              in _items ?? <(Map<String, dynamic>, ProductDetails)>[])
            Card(
              child: ListTile(
                title: Text('${tier['seat_count']} 个孩子名额'),
                subtitle: Text('${product.price}/月 · 自动续订'),
                trailing: FilledButton(
                  onPressed: disabled || !billing.canBuy
                      ? null
                      : () => _action(
                          () => billing.buy(
                            product,
                            tier['product_code'] as String,
                          ),
                        ),
                  child: const Text('订阅'),
                ),
              ),
            ),
          if (_items != null && _items!.isEmpty)
            const Text('暂无可购买档位，可恢复已有订阅或前往商店管理。'),
          TextButton(
            onPressed: disabled ? null : () => _action(billing.restore),
            child: const Text('恢复购买 / 重试验单'),
          ),
          TextButton(
            onPressed: disabled
                ? null
                : () => _action(() async {
                    if (!await launchUrl(
                      billing.adapter.managementUrl,
                      mode: LaunchMode.externalApplication,
                    )) {
                      throw StateError('无法打开订阅管理');
                    }
                  }),
            child: const Text('管理或取消自动续订'),
          ),
          TextButton(
            onPressed: disabled ? null : () => _action(_load),
            child: const Text('刷新订阅商品'),
          ),
          const Text('费用由当前商店账户支付；除非提前在商店取消，否则每月按所选档位自动扣款。取消后可使用至商店确认的到期时间。'),
          const SizedBox(height: 8),
          for (final link in [
            (const String.fromEnvironment('TERMS_URL'), '使用条款'),
            (const String.fromEnvironment('PRIVACY_URL'), '隐私政策'),
          ])
            if (link.$1.isNotEmpty)
              TextButton(
                onPressed: () => _action(() async {
                  if (!await launchUrl(
                    Uri.parse(link.$1),
                    mode: LaunchMode.externalApplication,
                  )) {
                    throw StateError('无法打开文档');
                  }
                }),
                child: Text(link.$2),
              ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('完成，返回家庭'),
          ),
        ],
      ),
    );
  }
}
