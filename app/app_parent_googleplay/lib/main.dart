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

class GoogleAdapter extends StoreAdapter {
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
  SubscriptionOfferDetailsWrapper? _offer(ProductDetails product) {
    if (product is! GooglePlayProductDetails ||
        product.subscriptionIndex == null) {
      return null;
    }
    return product.productDetails.subscriptionOfferDetails![product
        .subscriptionIndex!];
  }

  @override
  bool hasTrial(ProductDetails product) {
    final offer = _offer(product);
    if (offer == null ||
        offer.offerId == null ||
        offer.pricingPhases.length != 2) {
      return false;
    }
    final trial = offer.pricingPhases.first;
    return trial.billingPeriod == 'P30D' &&
        trial.priceAmountMicros == 0 &&
        trial.billingCycleCount == 1 &&
        trial.recurrenceMode == RecurrenceMode.finiteRecurring;
  }

  @override
  bool monthly(ProductDetails product) {
    final offer = _offer(product);
    if (offer == null ||
        offer.installmentPlanDetails != null ||
        offer.pricingPhases.isEmpty) {
      return false;
    }
    final price = offer.pricingPhases.last;
    return (offer.offerId == null && offer.pricingPhases.length == 1 ||
            hasTrial(product)) &&
        price.billingPeriod == 'P1M' &&
        price.priceAmountMicros > 0 &&
        price.recurrenceMode == RecurrenceMode.infiniteRecurring &&
        offer.pricingPhases.every(
          (phase) => phase.priceCurrencyCode == price.priceCurrencyCode,
        );
  }

  @override
  ProductDetails billingPrice(ProductDetails product) {
    final price = _offer(product)!.pricingPhases.last;
    return ProductDetails(
      id: product.id,
      title: product.title,
      description: product.description,
      price: price.formattedPrice,
      rawPrice: price.priceAmountMicros / 1000000,
      currencyCode: price.priceCurrencyCode,
    );
  }

  @override
  Future<PurchaseParam> parameters(
    ProductDetails product,
    Map<String, dynamic> intent,
  ) async {
    if (!monthly(product) || product is! GooglePlayProductDetails) {
      throw StateError(tr('商店商品配置已变更，请刷新页面'));
    }
    if (hasTrial(product) &&
        (intent['trial_eligible'] != true || intent['old_reference'] != null)) {
      throw StateError(tr('试用资格已变化，请刷新订阅商品'));
    }
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
      offerToken: product.offerToken,
      applicationUserName: intent['account_token'] as String,
      changeSubscriptionParam: change,
    );
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final consentManager = GdprConsentManager.I;
  await consentManager.init();
  GdprConsentManager.onConsentChanged = (granted) {
    updatePlayTelemetryConsent(analyticsGranted: granted);
  };
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
          extraAccountActionBuilder: (_) => const GdprPrivacySettingsTile(),
        ),
      ),
    ),
  );
  Telemetry.event(AppEvent.appReady);
}
