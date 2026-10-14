import 'dart:async';

import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:fluwx/fluwx.dart';

// One SDK instance owns the platform response stream throughout the app.
Fluwx? _wechat;

class PaymentScreen extends StatefulWidget {
  const PaymentScreen({super.key, required this.order});
  final Map<String, dynamic> order;

  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen>
    with WidgetsBindingObserver {
  late Map<String, dynamic> _order;
  FluwxCancelable? _subscriber;
  Timer? _poll;
  bool _busy = false;
  bool _querying = false;
  bool _finished = false;
  bool _awaitingResult = false;
  String? _message;
  int get _id => _order['order_id'] as int;
  bool get _demo => _order['payment_mode'] == 'demo';
  bool get _pending => _order['status'] == 'pending';

  @override
  void initState() {
    super.initState();
    _order = Map.of(widget.order);
    WidgetsBinding.instance.addObserver(this);
    if (!_demo) {
      _wechat ??= Fluwx();
      _subscriber = _wechat!.addSubscriber((response) {
        if (response is WeChatPaymentResponse) {
          _awaitingResult = response.errCode != -2;
          if (mounted) {
            setState(
              () => _message = response.errCode == -2
                  ? tr("已取消微信支付，可继续支付或关闭订单")
                  : tr("正在核对支付结果…"),
            );
          }
          _query();
        }
      });
    }
    _query();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _query();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _subscriber?.cancel();
    _poll?.cancel();
    super.dispose();
  }

  void _accept(Map<String, dynamic> order) {
    if (!mounted || _finished) return;
    setState(() {
      _order = order;
      if (order['status'] == 'closed') {
        _message = tr("订单已关闭，请返回后重新下单");
      } else if (order['status'] == 'pending' && _awaitingResult) {
        _awaitingResult = false;
        _message = tr("服务端尚未确认支付，可稍后刷新结果");
      }
    });
    if (order['status'] == 'paid') {
      _finished = true;
      _poll?.cancel();
      Navigator.pop(context, true);
    }
  }

  Future<void> _query() async {
    if (_querying || !mounted || !_pending) return;
    _querying = true;
    try {
      _accept(await Api.I.paymentOrder(_id));
    } on ApiException catch (error) {
      if (mounted) setState(() => _message = error.message);
    } catch (_) {
      if (mounted) setState(() => _message = tr("暂时无法查询，请稍后刷新支付结果"));
    } finally {
      _querying = false;
    }
  }

  Future<void> _pay() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      if (_demo) {
        _accept(await Api.I.confirmDemoPayment(_id));
        return;
      }
      final prepared = await Api.I.preparePayment(_id);
      if (!mounted) return;
      _accept(prepared);
      if (prepared['status'] != 'pending') return;
      final params = _order['payment_params'] as Map<String, dynamic>;
      const appId = String.fromEnvironment(
        'WECHAT_APP_ID',
        defaultValue: 'wx_demo_parent_app',
      );
      const link = String.fromEnvironment(
        'WECHAT_UNIVERSAL_LINK',
        defaultValue: 'https://demo.example.com/wechat/',
      );
      if (appId.contains('demo') || params['appId'] != appId) {
        throw StateError(tr("客户端微信 AppID 未配置或与服务端不一致"));
      }
      if (!await _wechat!.registerApi(appId: appId, universalLink: link)) {
        throw StateError(tr("微信支付初始化失败"));
      }
      if (!await _wechat!.isWeChatInstalled) {
        throw StateError(tr("请先安装微信，再继续支付"));
      }
      final launched = await _wechat!.pay(
        which: Payment(
          appId: params['appId'] as String,
          partnerId: params['partnerId'] as String,
          prepayId: params['prepayId'] as String,
          packageValue: params['packageValue'] as String,
          nonceStr: params['nonceStr'] as String,
          timestamp: int.parse(params['timeStamp'].toString()),
          sign: params['sign'] as String,
        ),
      );
      if (!launched) throw StateError(tr("无法打开微信支付，请稍后重试"));
      if (mounted) setState(() => _message = tr("请在微信完成支付，返回后将核对结果"));
      _poll?.cancel();
      var attempts = 0;
      _poll = Timer.periodic(const Duration(seconds: 3), (timer) {
        if (++attempts >= 20 || !mounted || !_pending) timer.cancel();
        _query();
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _message = error.message);
    } on StateError catch (error) {
      if (mounted) setState(() => _message = error.message.toString());
    } catch (_) {
      if (mounted) setState(() => _message = tr("支付未完成，可刷新结果或稍后继续支付"));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _close() async {
    setState(() => _busy = true);
    try {
      final result = await Api.I.closePaymentOrder(_id);
      if (!mounted) return;
      if (result['status'] == 'paid') {
        _accept(result);
      } else if (result['status'] == 'closed') {
        _finished = true;
        Navigator.pop(context, false);
      } else {
        setState(() => _message = tr("订单尚未关闭，请刷新结果后重试"));
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _message = error.message);
    } catch (_) {
      if (mounted) setState(() => _message = tr("暂时无法关闭订单，请稍后重试"));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final cents = _order['amount_cents'] as int;
    final monthlyTier = _order['billing_rule'] == 'monthly_tier_v1';
    return Scaffold(
      appBar: AppBar(title: Text(tr("确认订单"))),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Icon(
            _demo ? Icons.science_outlined : Icons.payment,
            size: 52,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 24),
          Text(
            monthlyTier
                ? tr("家庭月订阅 · {0} 个孩子名额", [_order['target_seat_count']])
                : _order['kind'] == 'subscription'
                ? tr("AI 助学 · 原规则续费订单")
                : tr("增加孩子名额 · 原规则订单"),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          Text(
            '¥${(cents / 100).toStringAsFixed(2)}',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineLarge,
          ),
          const SizedBox(height: 16),
          Text(
            _demo ? tr("演示支付 · 不会扣款，仅用于测试订阅流程") : tr("微信支付 · 金额已由服务端核算"),
            textAlign: TextAlign.center,
          ),
          if (monthlyTier) ...[
            const SizedBox(height: 12),
            Text(
              _order['kind'] == 'seat_add'
                  ? tr(
                      "本次购买新档位的完整月订阅，支付确认后立即增加名额，不按剩余天数补差，已付旧档位费用不抵扣或退款。新周期从确认支付起计一个自然月，已有更晚的到期时间保留。",
                    )
                  : tr("购买一个自然月的家庭订阅，不累加已有有效期。微信支付为单次购买，到期后需手动续订。"),
            ),
          ] else if (_order['kind'] == 'seat_add') ...[
            const SizedBox(height: 12),
            Text(tr("费用按当前订阅剩余天数折算，支付成功后增加名额。后续续费将包含新增名额费用。")),
          ],
          const SizedBox(height: 24),
          SelectableText(tr("订单号：{0}", [_order['out_trade_no']])),
          if (_message != null) ...[
            const SizedBox(height: 16),
            Text(trMessage(_message!)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy || !_pending ? null : _pay,
            child: Text(
              _busy
                  ? tr("处理中…")
                  : _demo
                  ? tr("确认演示支付")
                  : tr("使用微信支付"),
            ),
          ),
          TextButton(
            onPressed: _busy ? null : _query,
            child: Text(tr("刷新支付结果")),
          ),
          TextButton(
            onPressed: _busy || !_pending ? null : _close,
            child: Text(tr("关闭订单")),
          ),
          Text(tr("离开页面后订单会保留，下次点击续费或增加名额可继续处理。"), textAlign: TextAlign.center),
        ],
      ),
    );
  }
}
