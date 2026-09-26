import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

/// 孩子的设备管理：查看当前/历史设备，远程踢出（踢出后该设备上的登录态立即失效）。
class DeviceManageScreen extends StatefulWidget {
  final int studentId;
  final String studentName;
  const DeviceManageScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });

  @override
  State<DeviceManageScreen> createState() => _DeviceManageScreenState();
}

class _DeviceManageScreenState extends State<DeviceManageScreen> {
  List<dynamic>? _devices;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final list = await Api.I.studentDevices(widget.studentId);
      if (!mounted) return;
      setState(() {
        _devices = list;
        _error = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  Future<void> _revoke(Map<String, dynamic> device) async {
    final name = device['device_name'] as String? ?? '该设备';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('下线 $name？'),
        content: const Text('该设备上的孩子端会立即退出登录，需要重新绑定才能使用。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('下线'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await Api.I.revokeStudentDevice(
        widget.studentId,
        device['id'] as int,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('已下线 $name')),
      );
      _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final devices = _devices;
    return Scaffold(
      appBar: AppBar(title: Text('${widget.studentName} 的设备')),
      body: devices == null
          ? Center(
              child: _error == null
                  ? const CircularProgressIndicator()
                  : Text(_error!),
            )
          : devices.isEmpty
              ? const Center(child: Text('还没有设备绑定过这个孩子'))
              : ListView.separated(
                  padding: const EdgeInsets.all(12),
                  itemCount: devices.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (_, i) {
                    final d = devices[i] as Map<String, dynamic>;
                    final isCurrent = d['is_current'] == true;
                    final revoked = d['revoked_at'] != null;
                    final lastSeen = (d['last_seen_at'] as String?) ?? '';
                    return Card(
                      child: ListTile(
                        leading: Icon(
                          isCurrent ? Icons.phone_android : Icons.phone_disabled,
                          color: isCurrent ? Colors.green : Colors.grey,
                        ),
                        title: Text(d['device_name'] as String? ?? '未命名设备'),
                        subtitle: Text(
                          '${isCurrent ? "使用中" : revoked ? "已下线" : "历史设备"}'
                          '${lastSeen.isEmpty ? '' : ' · 最近活跃 ${lastSeen.substring(0, 16).replaceFirst('T', ' ')}'}',
                        ),
                        trailing: isCurrent
                            ? TextButton(
                                onPressed: () => _revoke(d),
                                child: const Text('下线'),
                              )
                            : null,
                      ),
                    );
                  },
                ),
    );
  }
}
