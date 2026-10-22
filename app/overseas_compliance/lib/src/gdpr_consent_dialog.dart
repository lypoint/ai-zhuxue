import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:url_launcher/url_launcher.dart';
import 'gdpr_consent_manager.dart';

/// Supported translations for GDPR dialogue across the app's seven languages.
class _GdprStrings {
  static const Map<String, Map<String, String>> _localized = {
    'zh-Hans': {
      'title': '数据隐私与合规声明',
      'body':
          '为向您和孩子提供更稳定的学习服务，我们需要收集基本的应用崩溃诊断与基础性能统计。我们承诺：不包含任何第三方广告，不跨应用追踪个人数据，严格遵守 GDPR 与未成年人保护法规。您可以随时在设置中修改授权。',
      'essential': '仅必要功能',
      'accept': '全部接受',
      'privacy_link': '阅读完整隐私政策',
    },
    'zh-Hant': {
      'title': '數據私隱與合規聲明',
      'body':
          '為向您和孩子提供更穩定的學習服務，我們需要收集基本的應用崩潰診斷與基礎性能統計。我們承諾：不包含任何第三方廣告，不跨應用追蹤個人數據，嚴格遵守 GDPR 與未成年人保護法規。您可以隨時在設定中修改授權。',
      'essential': '僅必要功能',
      'accept': '全部接受',
      'privacy_link': '閱讀完整隱私政策',
    },
    'en': {
      'title': 'Data Privacy & Consent',
      'body':
          'To provide a safe and stable learning experience for you and your child, we collect basic crash diagnostics and performance metrics. We promise: no third-party advertisements, no cross-app tracking, and strict adherence to GDPR and minor protection standards. You can change this preference anytime in Settings.',
      'essential': 'Essential Only',
      'accept': 'Accept All',
      'privacy_link': 'Read Privacy Policy',
    },
    'ja': {
      'title': 'データプライバシーと同意',
      'body':
          '安全で安定した学習体験を提供するため、基本的なクラッシュ診断とパフォーマンス測定値を収集します。第三者広告はなく、アプリ間のトラッキングも行いません。GDPRおよび未成年者保護基準を遵守します。この設定はいつでも変更できます。',
      'essential': '必須のみ',
      'accept': 'すべて同意',
      'privacy_link': 'プライバシーポリシー',
    },
    'ko': {
      'title': '데이터 개인정보 보호 및 동의',
      'body':
          '안전하고 안정적인 학습 환경을 제공하기 위해 기본 오류 진단 및 성능 지표를 수집합니다. 타사 광고나 앱 간 추적은 일체 없으며, GDPR 및 미성년자 보호 기준을 철저히 준수합니다. 설정에서 언제든지 변경할 수 있습니다.',
      'essential': '필수 항목만',
      'accept': '모두 동의',
      'privacy_link': '개인정보 처리방침',
    },
    'de': {
      'title': 'Datenschutz & Einwilligung',
      'body':
          'Um Ihnen und Ihrem Kind ein sicheres und stabiles Lernerlebnis zu bieten, erfassen wir grundlegende Absturzdiagnosen und Leistungsdaten. Wir versprechen: keine Werbung von Drittanbietern, kein App-übergreifendes Tracking und strikte Einhaltung der DSGVO. Sie können diese Einstellung jederzeit ändern.',
      'essential': 'Nur notwendige',
      'accept': 'Alle akzeptieren',
      'privacy_link': 'Datenschutzerklärung lesen',
    },
    'es': {
      'title': 'Privacidad de datos y consentimiento',
      'body':
          'Para ofrecer una experiencia de aprendizaje segura y estable, recopilamos diagnósticos básicos de fallos y rendimiento. Prometemos: sin publicidad de terceros, sin seguimiento entre aplicaciones y estricto cumplimiento del RGPD. Puede cambiar esta opción en Configuración en cualquier momento.',
      'essential': 'Solo esenciales',
      'accept': 'Aceptar todo',
      'privacy_link': 'Leer política de privacidad',
    },
  };

  static String get(String key, String tag) {
    final lang = _localized[tag] ?? _localized['en']!;
    return lang[key] ?? _localized['en']![key] ?? key;
  }
}

/// A clean, transparent GDPR consent modal dialogue.
class GdprConsentDialog extends StatelessWidget {
  final VoidCallback onAccepted;
  final VoidCallback onEssentialOnly;
  final String privacyUrl;

  const GdprConsentDialog({
    super.key,
    required this.onAccepted,
    required this.onEssentialOnly,
    this.privacyUrl = const String.fromEnvironment(
      'PRIVACY_URL',
      defaultValue: 'https://gker.net/privacy/',
    ),
  });

  /// Shows the dialog if consent has not been recorded yet.
  static Future<void> checkAndShow(
    BuildContext context, {
    String? privacyUrl,
    void Function(bool granted)? onDecision,
  }) async {
    final manager = GdprConsentManager.I;
    await manager.init();
    final required = await manager.isConsentRequired();
    if (!required) {
      onDecision?.call(manager.isAnalyticsGranted);
      return;
    }

    if (!context.mounted) return;

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => PopScope(
        canPop: false,
        child: GdprConsentDialog(
          privacyUrl: privacyUrl ??
              const String.fromEnvironment(
                'PRIVACY_URL',
                defaultValue: 'https://gker.net/privacy/',
              ),
          onAccepted: () async {
            await manager.saveConsent(grantAnalytics: true);
            if (dialogContext.mounted) Navigator.of(dialogContext).pop();
            onDecision?.call(true);
          },
          onEssentialOnly: () async {
            await manager.saveConsent(grantAnalytics: false);
            if (dialogContext.mounted) Navigator.of(dialogContext).pop();
            onDecision?.call(false);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tag = AppLanguage.I.tag;
    final title = _GdprStrings.get('title', tag);
    final body = _GdprStrings.get('body', tag);
    final essential = _GdprStrings.get('essential', tag);
    final accept = _GdprStrings.get('accept', tag);
    final privacyLink = _GdprStrings.get('privacy_link', tag);

    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Row(
        children: [
          Icon(Icons.shield_outlined, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              body,
              style: TextStyle(
                fontSize: 14,
                height: 1.5,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            InkWell(
              onTap: () async {
                final uri = Uri.tryParse(privacyUrl);
                if (uri != null && await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              },
              child: Text(
                '$privacyUrl ($privacyLink)',
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.primary,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ],
        ),
      ),
      actionsAlignment: MainAxisAlignment.end,
      actions: [
        TextButton(
          onPressed: onEssentialOnly,
          child: Text(essential),
        ),
        FilledButton(
          onPressed: onAccepted,
          child: Text(accept),
        ),
      ],
    );
  }
}
