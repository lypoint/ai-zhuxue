import 'package:flutter/material.dart';
import '../screens/review_screen.dart';
import '../screens/parent_favorites_screen.dart';
import '../screens/grades_screen.dart';

/// 家庭总览里的单个孩子卡片：改名、切换学段、进入收藏与全量审查。
class StudentReviewCard extends StatelessWidget {
  final Map<String, dynamic> student;
  final VoidCallback onRename;
  final VoidCallback? onRebind;
  final bool bindingInProgress;
  final VoidCallback onManageDevices;
  final Future<void> Function(String band) onGradeBandChanged;
  const StudentReviewCard({
    super.key,
    required this.student,
    required this.onRename,
    required this.onRebind,
    this.bindingInProgress = false,
    required this.onManageDevices,
    required this.onGradeBandChanged,
  });

  @override
  Widget build(BuildContext context) {
    final name = student['nickname'] as String? ?? '';
    final device = student['current_device'] as Map<String, dynamic>?;
    return Card(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.face),
            title: Text(name),
            subtitle: Text(
              '学段 ${student['grade_band']}${device == null ? '' : ' · 设备 ${device['name'] ?? ''}'}',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReviewScreen(
                  studentId: student['id'] as int,
                  studentName: name,
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: Wrap(
              alignment: WrapAlignment.end,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 4,
              children: [
                DropdownButton<String>(
                  value: student['grade_band'] as String,
                  underline: const SizedBox(),
                  items: const [
                    DropdownMenuItem(
                      value: '8-12',
                      child: Text('8-12岁', style: TextStyle(fontSize: 12)),
                    ),
                    DropdownMenuItem(
                      value: '12-16',
                      child: Text('12-16岁', style: TextStyle(fontSize: 12)),
                    ),
                    DropdownMenuItem(
                      value: '16-18',
                      child: Text('16-18岁', style: TextStyle(fontSize: 12)),
                    ),
                  ],
                  onChanged: (v) {
                    if (v == null || v == student['grade_band']) return;
                    onGradeBandChanged(v);
                  },
                ),
                IconButton(
                  icon: const Icon(Icons.edit, size: 20),
                  tooltip: '修改昵称',
                  onPressed: onRename,
                ),
                IconButton(
                  icon: const Icon(Icons.star_border, size: 20),
                  tooltip: '孩子的收藏',
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => ParentFavoritesScreen(
                        studentId: student['id'] as int,
                        studentName: name,
                      ),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.insights, size: 20),
                  tooltip: '成绩与评估',
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => GradesScreen(
                        studentId: student['id'] as int,
                        studentName: name,
                      ),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.devices_other, size: 20),
                  tooltip: '设备管理',
                  onPressed: onManageDevices,
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: Align(
              alignment: Alignment.centerRight,
              child: FilledButton.tonalIcon(
                onPressed: onRebind,
                icon: const Icon(Icons.qr_code_2, size: 18),
                label: Text(
                  bindingInProgress
                      ? '生成中…'
                      : device == null
                          ? '绑定设备'
                          : '重新绑定设备',
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
