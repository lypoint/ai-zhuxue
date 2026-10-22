import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'gdpr_consent_manager.dart';

/// Button or list tile for accessing GDPR consent preferences from user settings.
class GdprPrivacySettingsTile extends StatelessWidget {
  final VoidCallback? onConsentRevoked;
  const GdprPrivacySettingsTile({super.key, this.onConsentRevoked});

  @override
  Widget build(BuildContext context) {
    final manager = GdprConsentManager.I;
    return ValueListenableBuilder<bool?>(
      valueListenable: manager.analyticsGranted,
      builder: (context, granted, _) {
        final isGranted = granted ?? false;
        return OutlinedButton.icon(
          onPressed: () => _showDialog(context),
          icon: const Icon(Icons.privacy_tip_outlined),
          label: Text(
            isGranted ? tr("数据隐私与统计设置 (已授权)") : tr("数据隐私与统计设置 (已拒绝)"),
          ),
        );
      },
    );
  }

  void _showDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => const _GdprSettingsDialog(),
    );
  }
}

class _GdprSettingsDialog extends StatefulWidget {
  const _GdprSettingsDialog();
  @override
  State<_GdprSettingsDialog> createState() => _GdprSettingsDialogState();
}

class _GdprSettingsDialogState extends State<_GdprSettingsDialog> {
  late bool _analyticsGranted;

  @override
  void initState() {
    super.initState();
    _analyticsGranted = GdprConsentManager.I.isAnalyticsGranted;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Text(tr("数据隐私与统计授权")),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr("为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。"),
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 16),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(tr("统计与诊断数据收集")),
            subtitle: Text(
              _analyticsGranted ? tr("当前已允许收集匿名统计") : tr("当前仅运行必要功能，已停止统计"),
              style: const TextStyle(fontSize: 12),
            ),
            value: _analyticsGranted,
            onChanged: (val) async {
              setState(() => _analyticsGranted = val);
              await GdprConsentManager.I.saveConsent(grantAnalytics: val);
            },
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(tr("完成")),
        ),
      ],
    );
  }
}
