import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

class FamilyTimezoneScreen extends StatefulWidget {
  const FamilyTimezoneScreen({super.key, this.zone});
  final String? zone;
  @override
  State<FamilyTimezoneScreen> createState() => _FamilyTimezoneScreenState();
}

class _FamilyTimezoneScreenState extends State<FamilyTimezoneScreen> {
  String _query = '';
  bool _saving = false;
  Future<void> _save(String zone) async {
    setState(() => _saving = true);
    try {
      await Api.I.updateFamilyTimezone(zone);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e is ApiException ? e.message : tr('保存失败，请检查网络后重试')),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final zones = FamilyTime.zones
        .where((zone) => zone.toLowerCase().contains(_query.toLowerCase()))
        .toList();
    return Scaffold(
      appBar: AppBar(title: Text(tr('家庭时区'))),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              '${tr('学习日、每日额度和休息时段均按此时区计算，并处理夏令时变化。')}\n${tr('每 24 小时最多更改一次时区，已用额度会延续。')}',
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              enabled: !_saving,
              decoration: InputDecoration(
                labelText: tr('搜索时区'),
                hintText: 'Asia/Shanghai',
              ),
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (_saving) const LinearProgressIndicator(),
          Expanded(
            child: ListView.builder(
              itemCount: zones.length,
              itemBuilder: (_, index) => ListTile(
                title: Text(zones[index]),
                selected: zones[index] == widget.zone,
                trailing: zones[index] == widget.zone
                    ? const Icon(Icons.check)
                    : null,
                onTap: _saving ? null : () => _save(zones[index]),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
