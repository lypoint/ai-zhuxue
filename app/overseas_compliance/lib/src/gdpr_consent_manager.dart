import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Manages GDPR consent state and user transparency choices for overseas releases.
class GdprConsentManager {
  GdprConsentManager._();
  static final GdprConsentManager I = GdprConsentManager._();

  static const String _keyDecided = 'compliance_gdpr_decided';
  static const String _keyAnalytics = 'compliance_gdpr_analytics_granted';
  static const String _keyTimestamp = 'compliance_gdpr_timestamp';

  final ValueNotifier<bool?> analyticsGranted = ValueNotifier<bool?>(null);
  bool _initialized = false;

  /// Loads current consent state from persistent storage.
  Future<void> init() async {
    if (_initialized) return;
    final prefs = await SharedPreferences.getInstance();
    final decided = prefs.getBool(_keyDecided) ?? false;
    if (decided) {
      analyticsGranted.value = prefs.getBool(_keyAnalytics) ?? false;
    } else {
      analyticsGranted.value = null;
    }
    _initialized = true;
  }

  /// Whether the user has not yet submitted their consent choice.
  Future<bool> isConsentRequired() async {
    final prefs = await SharedPreferences.getInstance();
    return !(prefs.getBool(_keyDecided) ?? false);
  }

  /// Returns whether analytics data collection was granted by the user.
  /// If not yet decided, returns false by default for privacy-by-default compliance.
  bool get isAnalyticsGranted => analyticsGranted.value ?? false;

  /// Saves user's consent choice.
  Future<void> saveConsent({required bool grantAnalytics}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyDecided, true);
    await prefs.setBool(_keyAnalytics, grantAnalytics);
    await prefs.setInt(_keyTimestamp, DateTime.now().millisecondsSinceEpoch);
    analyticsGranted.value = grantAnalytics;
  }

  /// Revokes consent and reverts to essential-only processing.
  Future<void> revokeConsent() async {
    await saveConsent(grantAnalytics: false);
  }

  /// Resets saved state (mainly used for testing or resetting user preferences).
  Future<void> resetForTest() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyDecided);
    await prefs.remove(_keyAnalytics);
    await prefs.remove(_keyTimestamp);
    analyticsGranted.value = null;
    _initialized = false;
  }
}
