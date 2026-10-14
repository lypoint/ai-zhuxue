import 'dart:async';
import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:parent_store/store_billing.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeStore extends InAppPurchasePlatform {
  final events = StreamController<List<PurchaseDetails>>.broadcast(sync: true);
  int completed = 0;
  int launched = 0;
  @override
  Future<bool> buyNonConsumable({required PurchaseParam purchaseParam}) async {
    launched++;
    return true;
  }

  @override
  Stream<List<PurchaseDetails>> get purchaseStream => events.stream;
  @override
  Future<void> completePurchase(PurchaseDetails purchase) async {
    completed++;
  }
}

class FakeAdapter implements StoreAdapter {
  final store = FakeStore();
  @override
  String get channel => 'googleplay';
  @override
  InAppPurchasePlatform get platform => store;
  @override
  String reference(PurchaseDetails purchase) =>
      purchase.verificationData.serverVerificationData;
  @override
  bool monthly(ProductDetails product) => true;
  @override
  Future<PurchaseParam> parameters(
    ProductDetails product,
    Map<String, dynamic> intent,
  ) async => PurchaseParam(productDetails: product);
  @override
  Uri get managementUrl =>
      Uri.parse('https://play.google.com/store/account/subscriptions');
}

PurchaseDetails transaction(PurchaseStatus status) => PurchaseDetails(
  purchaseID: '123',
  productID: 'tier.10',
  transactionDate: '1',
  status: status,
  verificationData: PurchaseVerificationData(
    localVerificationData: '',
    serverVerificationData: 'signed-store-token',
    source: 'google_play',
  ),
)..pendingCompletePurchase = true;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'failed server verification retains transaction; retry completes only after verification',
    () async {
      SharedPreferences.setMockInitialValues({'token': 'guardian-token'});
      await Api.I.loadToken();
      var allowed = false;
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        expect(request.url.path, '/parent/billing/verify');
        expect(jsonDecode(request.body), {
          'channel': 'googleplay',
          'reference': 'signed-store-token',
        });
        return http.Response(
          allowed ? '{}' : '{"detail":"验单暂时失败"}',
          allowed ? 200 : 503,
        );
      });
      await http.runWithClient(() async {
        final adapter = FakeAdapter();
        final billing = StoreBilling(adapter);
        adapter.store.events.add([transaction(PurchaseStatus.purchased)]);
        await billing.retry();
        expect(calls, greaterThan(0));
        expect(adapter.store.completed, 0);
        expect(billing.verifiedCount, 0);
        expect(billing.canBuy, isFalse);
        allowed = true;
        await billing.retry();
        expect(adapter.store.completed, 1);
        expect(billing.verifiedCount, 1);
        expect(billing.canBuy, isTrue);
        await billing.retry();
        expect(adapter.store.completed, 1);
        billing.dispose();
        await adapter.store.events.close();
      }, () => client);
      client.close();
    },
  );

  test(
    'launched or pending purchase blocks a second charge until cancellation',
    () async {
      final client = MockClient(
        (request) async => http.Response(
          '{"product_id":"tier.10","account_token":"account"}',
          200,
        ),
      );
      await http.runWithClient(() async {
        final adapter = FakeAdapter();
        final billing = StoreBilling(adapter);
        final product = ProductDetails(
          id: 'tier.10',
          title: '10 seats',
          description: 'Monthly',
          price: '¥300',
          rawPrice: 300,
          currencyCode: 'CNY',
        );
        await billing.buy(product, 'family_monthly_10');
        await billing.buy(product, 'family_monthly_10');
        expect(adapter.store.launched, 1);
        expect(billing.canBuy, isFalse);
        adapter.store.events.add([transaction(PurchaseStatus.pending)]);
        expect(billing.canBuy, isFalse);
        adapter.store.events.add([transaction(PurchaseStatus.canceled)]);
        await billing.retry();
        expect(billing.canBuy, isTrue);
        expect(adapter.store.completed, 0);
        billing.dispose();
        await adapter.store.events.close();
      }, () => client);
      client.close();
    },
  );

  test(
    'pending and canceled transactions never grant rights; logged-out purchase waits for login',
    () async {
      Api.I.clearToken();
      var calls = 0;
      final client = MockClient((_) async {
        calls++;
        return http.Response('{}', 200);
      });
      await http.runWithClient(() async {
        final adapter = FakeAdapter();
        final billing = StoreBilling(adapter);
        adapter.store.events.add([
          transaction(PurchaseStatus.pending),
          transaction(PurchaseStatus.canceled),
        ]);
        await billing.retry();
        expect(calls, 0);
        adapter.store.events.add([transaction(PurchaseStatus.restored)]);
        await billing.retry();
        expect(calls, 0);
        SharedPreferences.setMockInitialValues({'token': 'restored-login'});
        await Api.I.loadToken();
        await billing.retry();
        expect(calls, 1);
        expect(adapter.store.completed, 1);
        billing.dispose();
        await adapter.store.events.close();
      }, () => client);
      client.close();
    },
  );
}
