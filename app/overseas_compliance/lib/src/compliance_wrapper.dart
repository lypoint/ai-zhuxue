import 'package:flutter/material.dart';
import 'gdpr_consent_dialog.dart';
import 'gdpr_consent_manager.dart';

/// Wraps the root app of overseas channels to orchestrate GDPR consent and post-consent flows (e.g. ATT).
class OverseasComplianceWrapper extends StatefulWidget {
  final Widget child;
  final GlobalKey<NavigatorState>? navigatorKey;
  final void Function(bool analyticsGranted)? onConsentDecision;
  final Future<void> Function()? onPostConsent;

  const OverseasComplianceWrapper({
    super.key,
    required this.child,
    this.navigatorKey,
    this.onConsentDecision,
    this.onPostConsent,
  });

  @override
  State<OverseasComplianceWrapper> createState() => _OverseasComplianceWrapperState();
}

class _OverseasComplianceWrapperState extends State<OverseasComplianceWrapper> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _runComplianceFlow());
  }

  Future<void> _runComplianceFlow() async {
    final manager = GdprConsentManager.I;
    await manager.init();

    final targetContext = widget.navigatorKey?.currentContext ??
        (mounted ? context : null);
    if (targetContext == null || !targetContext.mounted) return;

    await GdprConsentDialog.checkAndShow(
      targetContext,
      onDecision: (granted) {
        widget.onConsentDecision?.call(granted);
        widget.onPostConsent?.call();
      },
    );
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
