import 'package:flutter/material.dart';
import '../screens/review_screen.dart';
import '../screens/parent_favorites_screen.dart';
import '../screens/grades_screen.dart';

/// 家庭总览里的单个孩子卡片：改名、切换学段、进入收藏与全量审查。
class StudentReviewCard extends StatelessWidget {
  final Map<String, dynamic> student;
  final VoidCallback onRename;
  final VoidCallback onRebind;
  final Future<void> Function(String band) onGradeBandChanged;
  const StudentReviewCard({
    super.key,
    required this.student,
    required this.onRename,
    required this.onRebind,
    required this.onGradeBandChanged,
  });

  @override
  Widget build(BuildContext context) {
    final name = student['nickname'] as String? ?? '';
    final device = student['current_device'] as Map<String, dynamic>?;
    return Card(
      child: ListTile(
        leading: const Icon(Icons.face),
        title: Row(
          children: [
            Expanded(child: Text(name)),
            IconButton(
              icon: const Icon(Icons.edit, size: 16),
              tooltip: '修改昵称',
              onPressed: onRename,
            ),
          ],
        ),
        subtitle: Text(
          '学段 ${student['grade_band']}${device == null ? '' : ' · 设备 ${device['name'] ?? ''}'}',
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
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
              tooltip: '重新绑定设备',
              onPressed: onRebind,
            ),
            const Icon(Icons.chevron_right),
          ],
        ),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ReviewScreen(
              studentId: student['id'] as int,
              studentName: name,
            ),
          ),
        ),
      ),
    );
  }
}
