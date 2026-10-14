import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
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
  final bool updatesDisabled;
  const StudentReviewCard({
    super.key,
    required this.student,
    required this.onRename,
    required this.onRebind,
    this.bindingInProgress = false,
    required this.onManageDevices,
    required this.onGradeBandChanged,
    this.updatesDisabled = false,
  });

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final name = student['nickname'] as String? ?? '';
    final device = student['current_device'] as Map<String, dynamic>?;
    final actionStyle = TextButton.styleFrom(
      visualDensity: VisualDensity.compact,
      padding: const EdgeInsets.symmetric(horizontal: 6),
    );
    return Card(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: CircleAvatar(
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              foregroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
              child: const Icon(Icons.face_outlined),
            ),
            title: Text(
              name,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
            subtitle: Text(
              tr("{0} 岁 · {1}", [
                student['grade_band'],
                device == null ? tr("待绑定设备") : device['name'] ?? tr("设备已绑定"),
              ]),
            ),
            trailing: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.chat_bubble_outline_rounded,
                  color: Theme.of(context).colorScheme.primary,
                  size: 20,
                ),
                const SizedBox(height: 4),
                Text(
                  tr("对话"),
                  style: TextStyle(
                    fontSize: 11,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
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
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: [
                LayoutBuilder(
                  builder: (context, constraints) {
                    final columns =
                        constraints.maxWidth < 290 ||
                            MediaQuery.textScalerOf(context).scale(14) > 18
                        ? 2
                        : 3;
                    final tileWidth =
                        (constraints.maxWidth - (columns - 1) * 8) / columns;
                    return Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _learningAction(
                          context,
                          width: tileWidth,
                          icon: Icons.star_border,
                          label: tr("收藏"),
                          color: const Color(0xFFA67327),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => ParentFavoritesScreen(
                                studentId: student['id'] as int,
                                studentName: name,
                              ),
                            ),
                          ),
                        ),
                        _learningAction(
                          context,
                          width: tileWidth,
                          icon: Icons.auto_awesome,
                          label: tr("学习奖励"),
                          color: const Color(0xFF6579AF),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => LearningScreen(
                                studentId: student['id'] as int,
                              ),
                            ),
                          ),
                        ),
                        _learningAction(
                          context,
                          width: tileWidth,
                          icon: Icons.insights,
                          label: tr("成绩"),
                          color: const Color(0xFF28786B),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => GradesScreen(
                                studentId: student['id'] as int,
                                studentName: name,
                              ),
                            ),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          if (device == null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: onRebind,
                  icon: const Icon(Icons.qr_code_2, size: 18),
                  label: Text(bindingInProgress ? tr("生成中…") : tr("绑定设备")),
                ),
              ),
            ),
          ExpansionTile(
            key: PageStorageKey('student-${student['id']}-details'),
            title: Text(
              tr("资料与设备"),
              style: TextStyle(
                fontSize: 13,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            tilePadding: const EdgeInsets.symmetric(horizontal: 16),
            childrenPadding: const EdgeInsets.symmetric(horizontal: 12),
            shape: const Border(),
            collapsedShape: const Border(),
            children: [
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(tr("学段")),
                      const SizedBox(width: 8),
                      DropdownButton<String>(
                        value: student['grade_band'] as String,
                        underline: const SizedBox(),
                        items: [
                          DropdownMenuItem(
                            value: '8-12',
                            child: Text(
                              tr("8-12岁"),
                              style: TextStyle(fontSize: 12),
                            ),
                          ),
                          DropdownMenuItem(
                            value: '12-16',
                            child: Text(
                              tr("12-16岁"),
                              style: TextStyle(fontSize: 12),
                            ),
                          ),
                          DropdownMenuItem(
                            value: '16-18',
                            child: Text(
                              tr("16-18岁"),
                              style: TextStyle(fontSize: 12),
                            ),
                          ),
                        ],
                        onChanged: updatesDisabled
                            ? null
                            : (v) {
                                if (v == null || v == student['grade_band']) {
                                  return;
                                }
                                onGradeBandChanged(v);
                              },
                      ),
                    ],
                  ),
                  TextButton.icon(
                    icon: const Icon(Icons.edit, size: 20),
                    label: Text(tr("改名")),
                    style: actionStyle,
                    onPressed: updatesDisabled ? null : onRename,
                  ),
                ],
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  icon: const Icon(Icons.devices_other, size: 20),
                  label: Text(tr("设备")),
                  style: actionStyle,
                  onPressed: onManageDevices,
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                child: Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton.tonalIcon(
                    onPressed: onRebind,
                    icon: const Icon(Icons.qr_code_2, size: 18),
                    label: Text(
                      bindingInProgress
                          ? tr("生成中…")
                          : device == null
                          ? tr("生成绑定码")
                          : tr("重新绑定设备"),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _learningAction(
    BuildContext context, {
    required double width,
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onPressed,
  }) {
    return SizedBox(
      width: width,
      child: TextButton(
        style: TextButton.styleFrom(
          foregroundColor: Theme.of(context).colorScheme.onSurface,
          backgroundColor: color.withValues(alpha: .06),
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        onPressed: onPressed,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}
