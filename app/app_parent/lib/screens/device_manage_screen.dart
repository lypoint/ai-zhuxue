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
  bool _loading = false;
  int? _revokingId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await Api.I.studentDevices(widget.studentId);
      if (!mounted) return;
      setState(() {
        _devices = list;
        _error = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      if (_devices == null) {
        setState(() => _error = e.message);
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('刷新设备列表失败：${e.message}')));
      }
    } catch (_) {
      if (!mounted) return;
      if (_devices == null) {
        setState(() => _error = '设备列表加载失败，请检查网络后重试');
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('刷新设备列表失败，请检查网络后重试')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _revoke(Map<String, dynamic> device) async {
    if (_revokingId != null) return;
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
    if (_revokingId != null) return;
    final deviceId = device['id'] as int;
    setState(() => _revokingId = deviceId);
    try {
      await Api.I.revokeStudentDevice(widget.studentId, deviceId);
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('已下线 $name')));
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('下线失败，请检查网络后重试')));
      }
    } finally {
      if (mounted) setState(() => _revokingId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final devices = _devices;
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.studentName} 的设备'),
        actions: [
          IconButton(
            tooltip: '刷新设备列表',
            onPressed: _loading || _revokingId != null ? null : _load,
            icon: _loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: devices == null
          ? Center(
              child: _error == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!),
                        TextButton(onPressed: _load, child: const Text('重试')),
                      ],
                    ),
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
                      '${isCurrent
                          ? "使用中"
                          : revoked
                          ? "已下线"
                          : "历史设备"}'
                      '${lastSeen.isEmpty ? '' : ' · 最近活跃 ${(lastSeen.length > 16 ? lastSeen.substring(0, 16) : lastSeen).replaceFirst('T', ' ')}'}',
                    ),
                    trailing: isCurrent
                        ? TextButton(
                            onPressed: _revokingId == null
                                ? () => _revoke(d)
                                : null,
                            child: _revokingId == d['id']
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Text('下线'),
                          )
                        : null,
                  ),
                );
              },
            ),
    );
  }
}
