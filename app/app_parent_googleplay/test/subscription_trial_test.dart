import 'package:app_parent_googleplay/main.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_android/billing_client_wrappers.dart';

PricingPhaseWrapper phase({
  String period = 'P1M',
  int micros = 9990000,
  int cycles = 0,
  RecurrenceMode recurrence = RecurrenceMode.infiniteRecurring,
}) => PricingPhaseWrapper(
  billingCycleCount: cycles,
  billingPeriod: period,
  formattedPrice: micros == 0 ? 'Free' : r'$9.99',
  priceAmountMicros: micros,
  priceCurrencyCode: 'USD',
  recurrenceMode: recurrence,
);

List<GooglePlayProductDetails> products({
  String trialPeriod = 'P30D',
  int trialPrice = 0,
}) => GooglePlayProductDetails.fromProductDetails(
  ProductDetailsWrapper(
    description: 'Monthly',
    name: 'Family',
    productId: 'family.1',
    productType: ProductType.subs,
    title: 'Family',
    subscriptionOfferDetails: [
      SubscriptionOfferDetailsWrapper(
        basePlanId: 'monthly',
        offerTags: [],
        offerIdToken: 'paid-token',
        pricingPhases: [phase()],
      ),
      SubscriptionOfferDetailsWrapper(
        basePlanId: 'monthly',
        offerId: 'trial-30d',
        offerTags: [],
        offerIdToken: 'trial-token',
        pricingPhases: [
          phase(
            period: trialPeriod,
            micros: trialPrice,
            cycles: 1,
            recurrence: RecurrenceMode.finiteRecurring,
          ),
          phase(),
        ],
      ),
    ],
  ),
);

void main() {
  final adapter = GoogleAdapter();
  test(
    'eligible families receive the exact 30-day offer and see its recurring price',
    () async {
      final items = products();
      final selected = adapter.selectMonthly(items, allowTrial: true)!;
      expect(adapter.hasTrial(selected), isTrue);
      expect(selected.rawPrice, 0);
      expect(adapter.billingPrice(selected).price, r'$9.99');
      final parameter = await adapter.parameters(selected, {
        'account_token': 'family',
        'trial_eligible': true,
      });
      expect((parameter as GooglePlayPurchaseParam).offerToken, 'trial-token');
    },
  );
  test('returning families and upgrades select paid base plans', () async {
    final selected = adapter.selectMonthly(products(), allowTrial: false)!;
    expect(adapter.hasTrial(selected), isFalse);
    final parameter = await adapter.parameters(selected, {
      'account_token': 'family',
      'trial_eligible': false,
    });
    expect((parameter as GooglePlayPurchaseParam).offerToken, 'paid-token');
  });
  test(
    'calendar-month, shorter, and paid introductory phases do not qualify',
    () {
      for (final period in ['P1M', 'P7D']) {
        expect(
          adapter.hasTrial(
            adapter.selectMonthly(
              products(trialPeriod: period),
              allowTrial: true,
            )!,
          ),
          isFalse,
        );
      }
      expect(
        adapter.hasTrial(
          adapter.selectMonthly(
            products(trialPrice: 1000000),
            allowTrial: true,
          )!,
        ),
        isFalse,
      );
    },
  );
  test(
    'stale eligibility never silently falls back to an immediate charge',
    () async {
      final trial = adapter.selectMonthly(products(), allowTrial: true)!;
      await expectLater(
        adapter.parameters(trial, {'trial_eligible': false}),
        throwsStateError,
      );
      await expectLater(
        adapter.parameters(trial, {
          'trial_eligible': true,
          'old_reference': 'old',
        }),
        throwsStateError,
      );
    },
  );
}
