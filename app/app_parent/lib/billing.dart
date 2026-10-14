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
