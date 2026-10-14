import 'package:app_core/app_core.dart';

/// 围栏流水的中文标签映射（家长审查界面展示用）。
Map<String, String> get fenceStageLabel => {
  'whitelist': tr('白名单'),
  'classifier': tr('分类'),
  'second_pass': tr('复核'),
  'policy': tr('处置'),
};

Map<String, String> get fenceDecisionLabel => {
  'allow': tr('放行'),
  'rewrite': tr('改写'),
  'reject': tr('拦截'),
};

Map<String, String> get fenceCategoryLabel => {
  'study': tr('学习'),
  'entertainment': tr('娱乐'),
  'sensitive': tr('敏感'),
  'other': tr('其他'),
};
