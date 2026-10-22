import 'package:flutter/material.dart';
import 'package:overseas_compliance/overseas_compliance.dart';
import 'package:play_telemetry/play_telemetry.dart';
import 'google_login_screen.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/billing.dart';
import 'package:app_parent/parent_app.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_android/billing_client_wrappers.dart';
import 'package:parent_store/store_billing.dart';

class GoogleAdapter implements StoreAdapter {
  @override
  String get channel => 'googleplay';
  @override
  InAppPurchasePlatform get platform => InAppPurchasePlatform.instance;
  @override
  Uri get managementUrl =>
      Uri.parse('https://play.google.com/store/account/subscriptions');
  @override
  String reference(PurchaseDetails purchase) =>
      purchase.verificationData.serverVerificationData;
  @override
  bool monthly(ProductDetails product) {
    if (product is! GooglePlayProductDetails ||
        product.subscriptionIndex == null) {
      return false;
    }
    final offer = product
        .productDetails
        .subscriptionOfferDetails![product.subscriptionIndex!];
    return offer.offerId == null &&
        offer.pricingPhases.length == 1 &&
        offer.pricingPhases.single.billingPeriod == 'P1M' &&
        offer.pricingPhases.single.recurrenceMode ==
            RecurrenceMode.infiniteRecurring;
  }

  @override
  Future<PurchaseParam> parameters(
    ProductDetails product,
    Map<String, dynamic> intent,
  ) async {
    ChangeSubscriptionParam? change;
    if (intent['old_reference'] != null) {
      final purchases =
          await (InAppPurchasePlatformAddition.instance
                  as InAppPurchaseAndroidPlatformAddition)
              .queryPastPurchases();
      if (purchases.error != null) throw StateError(tr("无法查询原订阅，请先恢复购买"));
      final old = purchases.pastPurchases
          .where((p) => reference(p) == intent['old_reference'])
          .toList();
      if (old.length != 1) throw StateError(tr("当前 Google 账户未找到原订阅，请切换原商店账号"));
      change = ChangeSubscriptionParam(
        oldPurchaseDetails: old.single,
        replacementMode: ReplacementMode.chargeFullPrice,
      );
    }
    return GooglePlayPurchaseParam(
      productDetails: product,
      applicationUserName: intent['account_token'] as String,
      changeSubscriptionParam: change,
    );
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final consentManager = GdprConsentManager.I;
  await consentManager.init();
  await initializePlayTelemetry(
    initialAnalyticsConsent: consentManager.isAnalyticsGranted,
  );
  await AppLanguage.I.load();
  InAppPurchaseAndroidPlatform.registerPlatform();
  final billing = StoreBilling(GoogleAdapter());
  Api.I.channel = 'googleplay';
  await Api.I.loadToken();
  await billing.retry();
  final navigatorKey = GlobalKey<NavigatorState>();
  runApp(
    OverseasComplianceWrapper(
      navigatorKey: navigatorKey,
      onConsentDecision: (granted) {
        updatePlayTelemetryConsent(analyticsGranted: granted);
      },
      child: BillingScope(
        billing: billing,
        child: ParentApp(
          navigatorKey: navigatorKey,
          loginBuilder: (_) => const GoogleLoginScreen(),
        ),
      ),
    ),
  );
  Telemetry.event(AppEvent.appReady);
}
