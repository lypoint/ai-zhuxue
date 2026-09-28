import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'chat_screen.dart';

String? normalizeBindCode(String? value) {
  final code = value?.trim().toUpperCase();
  return code != null && RegExp(r'^[0-9A-F]{8}$').hasMatch(code) ? code : null;
}

/// 学生端首屏：输入或扫描家长端绑定码，激活并进入学习聊天。
class BindScreen extends StatefulWidget {
  const BindScreen({super.key});
  @override
  State<BindScreen> createState() => _BindScreenState();
}

class _BindScreenState extends State<BindScreen> {
  final _codeCtrl = TextEditingController();
  String? _error;
  bool _loading = false;

  Future<void> _scan() async {
    final code = await Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (_) => const _BindQrScanner()));
    if (!mounted || code == null) return;
    _codeCtrl.text = code;
    await _bind();
  }

  Future<void> _bind() async {
    final code = normalizeBindCode(_codeCtrl.text);
    if (code == null) {
      setState(() => _error = '请输入家长端提供的 8 位绑定码');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final installationId = await Api.I.installationId();
      await Api.I.studentLogin(code, installationId, '我的孩子');
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const ChatScreen()));
    } on ApiException catch (e) {
      final message = switch (e.message) {
        'bind code invalid or expired' => '绑定码无效或已过期，请家长重新生成',
        'bind code already used' => '绑定码已使用，请家长重新生成',
        _ => e.message,
      };
      if (mounted) setState(() => _error = message);
    } catch (_) {
      if (mounted) setState(() => _error = '连接失败，请检查网络后重试');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('开始学习')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFE8F6F1), Color(0xFFF6F8FB)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
          children: [
            Center(
              child: Container(
                width: 68,
                height: 68,
                decoration: BoxDecoration(
                  color: const Color(0xFF2F8B7D),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Image.asset(
                  'assets/logo-mark.png',
                  package: 'app_core',
                  color: Colors.white,
                  semanticLabel: 'AI 助学',
                ),
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              '和 AI 一起，把问题学会',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 25, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Text(
              '这是一个只聊学习的受保护空间',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 28),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      '输入家长端绑定码',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      '家长在家长端点击右上角二维码即可生成',
                      style: TextStyle(fontSize: 13, color: Colors.black54),
                    ),
                    const SizedBox(height: 18),
                    TextField(
                      controller: _codeCtrl,
                      textAlign: TextAlign.center,
                      textCapitalization: TextCapitalization.characters,
                      style: const TextStyle(
                        fontSize: 24,
                        letterSpacing: 4,
                        fontWeight: FontWeight.w700,
                      ),
                      decoration: InputDecoration(
                        hintText: 'A3F9C2B1',
                        prefixIcon: const Icon(Icons.qr_code_2),
                        errorText: _error,
                      ),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: _loading ? null : _scan,
                      icon: const Icon(Icons.qr_code_scanner),
                      label: const Text('扫描家长端二维码'),
                    ),
                    const SizedBox(height: 8),
                    FilledButton.icon(
                      onPressed: _loading ? null : _bind,
                      icon: const Icon(Icons.school_outlined),
                      label: Text(_loading ? '绑定中…' : '绑定并开始学习'),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BindQrScanner extends StatefulWidget {
  const _BindQrScanner();

  @override
  State<_BindQrScanner> createState() => _BindQrScannerState();
}

class _BindQrScannerState extends State<_BindQrScanner> {
  bool _handled = false;
  bool _invalid = false;

  void _onDetect(BarcodeCapture capture) {
    if (!mounted || _handled || capture.barcodes.isEmpty) return;
    for (final barcode in capture.barcodes) {
      final code = normalizeBindCode(barcode.rawValue);
      if (code != null) {
        _handled = true;
        Navigator.of(context).pop(code);
        return;
      }
    }
    if (!_invalid) setState(() => _invalid = true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('扫描绑定二维码')),
      body: Stack(
        children: [
          Positioned.fill(
            child: MobileScanner(
              onDetect: _onDetect,
              errorBuilder: (context, error) => const ColoredBox(
                color: Colors.black,
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      '无法使用相机，请检查相机权限，或返回手动输入绑定码',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ),
              ),
            ),
          ),
          Center(
            child: Container(
              width: 220,
              height: 220,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 3),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  _invalid ? '这不是家长端的绑定二维码，请重新扫描' : '将家长端二维码放入框内',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
