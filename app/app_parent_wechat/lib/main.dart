import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/parent_app.dart';
import 'package:app_parent/billing.dart';
import 'wechat_billing.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppLanguage.I.load();
  Api.I.channel = 'wechat';
  await Api.I.loadToken();
  runApp(BillingScope(billing: WechatBilling(), child: const ParentApp()));
}
