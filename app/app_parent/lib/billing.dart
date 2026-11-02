import 'package:flutter/material.dart';

abstract class ParentBilling extends ChangeNotifier {
  int get revision => 0;
  String get channel;
  Future<void> recover() async {}
  Future<bool?> purchase(BuildContext context, String kind);
}

class BillingScope extends InheritedWidget {
  const BillingScope({super.key, required this.billing, required super.child});
  final ParentBilling billing;
  static ParentBilling of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<BillingScope>()!.billing;
  @override
  bool updateShouldNotify(BillingScope oldWidget) =>
      billing != oldWidget.billing;
}

/// Management follows the verified entitlement source, independently of this app's store.
Uri? subscriptionManagementUri(String? provider, {String? waffoUrl}) {
  if (provider == 'appstore') {
    return Uri.parse('https://apps.apple.com/account/subscriptions');
  }
  if (provider == 'googleplay') {
    return Uri.parse('https://play.google.com/store/account/subscriptions');
  }
  if (provider != 'waffo') return null;
  final url = Uri.parse(waffoUrl!);
  if (url.scheme != 'https' ||
      url.host != 'pancake.waffo.ai' ||
      url.hasPort ||
      url.userInfo.isNotEmpty ||
      !url.path.startsWith('/consumer/portal/')) {
    throw const FormatException('Invalid subscription portal');
  }
  return url;
}
