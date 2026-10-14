import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/billing.dart';
import 'package:app_parent/parent_app.dart';
import 'package:in_app_purchase_storekit/in_app_purchase_storekit.dart';
import 'package:in_app_purchase_storekit/store_kit_2_wrappers.dart';
import 'package:parent_store/store_billing.dart';

class AppleAdapter implements StoreAdapter {
  @override
  String get channel => 'appstore';
  @override
  InAppPurchasePlatform get platform => InAppPurchasePlatform.instance;
  @override
  Uri get managementUrl =>
      Uri.parse('https://apps.apple.com/account/subscriptions');
  @override
  String reference(PurchaseDetails purchase) => purchase.purchaseID!;
  @override
  bool monthly(ProductDetails product) {
    if (product is! AppStoreProduct2Details) return false;
    final period = product.sk2Product.subscription?.subscriptionPeriod;
    return product.sk2Product.type == SK2ProductType.autoRenewable &&
        period?.value == 1 &&
        period?.unit == SK2SubscriptionPeriodUnit.month;
  }

  @override
  Future<PurchaseParam> parameters(
    ProductDetails product,
    Map<String, dynamic> intent,
  ) async => PurchaseParam(
    productDetails: product,
    applicationUserName: intent['account_token'] as String,
  );
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppLanguage.I.load();
  InAppPurchaseStoreKitPlatform.registerPlatform();
  final billing = StoreBilling(AppleAdapter());
  await Api.I.loadToken();
  await billing.retry();
  runApp(BillingScope(billing: billing, child: const ParentApp()));
}
