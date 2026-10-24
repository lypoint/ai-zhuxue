import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'gdpr_consent_manager.dart';

String _localTr(String text) {
  final translated = tr(text);
  if (translated != text) return translated;
  final tag = AppLanguage.I.tag;
  return _settingsStrings[tag]?[text] ??
      (tag.startsWith('zh') ? text : _settingsStrings['en']?[text] ?? text);
}

const Map<String, Map<String, String>> _settingsStrings = {
  'zh-Hans': {
    '数据隐私与统计设置 (已授权)': '数据隐私与统计设置 (已授权)',
    '数据隐私与统计设置 (已拒绝)': '数据隐私与统计设置 (已拒绝)',
    '数据隐私与统计授权': '数据隐私与统计授权',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。',
    '统计与诊断数据收集': '统计与诊断数据收集',
    '当前已允许收集匿名统计': '当前已允许收集匿名统计',
    '当前仅运行必要功能，已停止统计': '当前仅运行必要功能，已停止统计',
    '完成': '完成',
  },
  'zh-Hant': {
    '数据隐私与统计设置 (已授权)': '數據私隱與統計設定 (已授權)',
    '数据隐私与统计设置 (已拒绝)': '數據私隱與統計設定 (已拒絕)',
    '数据隐私与统计授权': '數據私隱與統計授權',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        '為了持續改進助學服務並定位故障，我們在徵得您同意後會收集匿名使用統計與崩潰日誌。您可隨時在此開啟或撤回授權。',
    '统计与诊断数据收集': '統計與診斷數據收集',
    '当前已允许收集匿名统计': '目前已允許收集匿名統計',
    '当前仅运行必要功能，已停止统计': '目前僅運行必要功能，已停止統計',
    '完成': '完成',
  },
  'en': {
    '数据隐私与统计设置 (已授权)': 'Data Privacy & Analytics (Granted)',
    '数据隐私与统计设置 (已拒绝)': 'Data Privacy & Analytics (Denied)',
    '数据隐私与统计授权': 'Data Privacy & Analytics Consent',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        'To continuously improve learning services and diagnose issues, we collect anonymous usage statistics and crash logs with your consent. You may grant or withdraw permission here at any time.',
    '统计与诊断数据收集': 'Analytics & Diagnostic Data Collection',
    '当前已允许收集匿名统计': 'Anonymous analytics collection is currently enabled',
    '当前仅运行必要功能，已停止统计': 'Essential features only; analytics collection is stopped',
    '完成': 'Done',
  },
  'ja': {
    '数据隐私与统计设置 (已授权)': 'データプライバシーと統計設定 (許可済み)',
    '数据隐私与统计设置 (已拒绝)': 'データプライバシーと統計設定 (拒否済み)',
    '数据隐私与统计授权': 'データプライバシーと統計の同意',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        '学習サービスの継続的な改善および障害対応のため、お客様の同意のもと匿名の利用統計およびクラッシュログを収集します。この設定はいつでも有効化または取り消しが可能です。',
    '统计与诊断数据收集': '統計および診断データの収集',
    '当前已允许收集匿名统计': '現在、匿名の統計収集が許可されています',
    '当前仅运行必要功能，已停止统计': '現在、必須機能のみ動作しており、統計収集は停止しています',
    '完成': '完了',
  },
  'ko': {
    '数据隐私与统计设置 (已授权)': '데이터 개인정보 보호 및 통계 설정 (허용됨)',
    '数据隐私与统计设置 (已拒绝)': '데이터 개인정보 보호 및 통계 설정 (거부됨)',
    '数据隐私与统计授权': '데이터 개인정보 보호 및 통계 동의',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        '학습 서비스를 지속적으로 개선하고 장애를 진단하기 위해 귀하의 동의를 얻어 익명 사용 통계 및 충돌 로그를 수집합니다. 언제든지 여기서 동의를 활성화하거나 철회할 수 있습니다.',
    '统计与诊断数据收集': '통계 및 진단 데이터 수집',
    '当前已允许收集匿名统计': '현재 익명 통계 수집이 허용되어 있습니다',
    '当前仅运行必要功能，已停止统计': '현재 필수 기능만 실행 중이며 통계 수집이 중지되었습니다',
    '完成': '완료',
  },
  'de': {
    '数据隐私与统计设置 (已授权)': 'Datenschutz- & Analyseeinstellungen (Erteilt)',
    '数据隐私与统计设置 (已拒绝)': 'Datenschutz- & Analyseeinstellungen (Abgelehnt)',
    '数据隐私与统计授权': 'Einwilligung in Datenschutz & Analysen',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        'Um den Lerndienst kontinuierlich zu verbessern und Probleme zu diagnostizieren, erfassen wir mit Ihrer Einwilligung anonyme Nutzungsstatistiken und Absturzberichte. Sie können diese Berechtigung hier jederzeit aktivieren oder widerrufen.',
    '统计与诊断数据收集': 'Erfassung von Analyse- und Diagnosedaten',
    '当前已允许收集匿名统计': 'Anonyme Statistikerfassung ist derzeit aktiviert',
    '当前仅运行必要功能，已停止统计': 'Nur wesentliche Funktionen aktiv; Statistikerfassung gestoppt',
    '完成': 'Fertig',
  },
  'es': {
    '数据隐私与统计设置 (已授权)': 'Privacidad y estadísticas (Concedido)',
    '数据隐私与统计设置 (已拒绝)': 'Privacidad y estadísticas (Denegado)',
    '数据隐私与统计授权': 'Consentimiento de privacidad y estadísticas',
    '为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。':
        'Para mejorar continuamente el servicio y solucionar fallos, recopilamos estadísticas anónimas e informes de errores con su consentimiento. Puede activar o revocar este permiso aquí en cualquier momento.',
    '统计与诊断数据收集': 'Recopilación de estadísticas y diagnósticos',
    '当前已允许收集匿名统计': 'Actualmente se permite la recopilación de estadísticas anónimas',
    '当前仅运行必要功能，已停止统计': 'Solo funciones esenciales activas; estadísticas detenidas',
    '完成': 'Listo',
  },
};

/// Button or list tile for accessing GDPR consent preferences from user settings.
class GdprPrivacySettingsTile extends StatelessWidget {
  final VoidCallback? onConsentRevoked;
  const GdprPrivacySettingsTile({super.key, this.onConsentRevoked});

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final manager = GdprConsentManager.I;
    return ValueListenableBuilder<bool?>(
      valueListenable: manager.analyticsGranted,
      builder: (context, granted, _) {
        final isGranted = granted ?? false;
        return OutlinedButton.icon(
          onPressed: () => _showDialog(context),
          icon: const Icon(Icons.privacy_tip_outlined),
          label: Text(
            isGranted
                ? _localTr("数据隐私与统计设置 (已授权)")
                : _localTr("数据隐私与统计设置 (已拒绝)"),
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
    AppLanguage.watch(context);
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Text(_localTr("数据隐私与统计授权")),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _localTr("为了持续改进助学服务并定位故障，我们在征得您同意后会收集匿名使用统计与崩溃日志。您可随时在此开启或撤回授权。"),
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 16),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(_localTr("统计与诊断数据收集")),
            subtitle: Text(
              _analyticsGranted
                  ? _localTr("当前已允许收集匿名统计")
                  : _localTr("当前仅运行必要功能，已停止统计"),
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
          child: Text(_localTr("完成")),
        ),
      ],
    );
  }
}
