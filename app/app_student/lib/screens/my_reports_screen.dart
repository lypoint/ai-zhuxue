import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import '../widgets/student_page_state.dart';

class MyReportsScreen extends StatefulWidget {
  const MyReportsScreen({super.key});

  @override
  State<MyReportsScreen> createState() => _MyReportsScreenState();
}

class _MyReportsScreenState extends State<MyReportsScreen> {
  late Future<List<dynamic>> _reports = Api.I.myReports();

  void _reload() => setState(() => _reports = Api.I.myReports());

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr("我的举报")),
        actions: [
          IconButton(
            tooltip: tr("刷新举报"),
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: FutureBuilder<List<dynamic>>(
        future: _reports,
        builder: (context, snapshot) {
          if (!snapshot.hasData && !snapshot.hasError) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final error = snapshot.error;
            final unavailable =
                error is ApiException &&
                error.status == 404 &&
                error.rawMessage == 'Not Found';
            return StudentPageState(
              icon: Icons.wifi_off_rounded,
              title: unavailable ? tr("举报服务暂未上线") : tr("举报记录加载失败"),
              description: unavailable ? tr("请稍后再试") : tr("请检查网络后重试"),
              onRetry: _reload,
            );
          }
          final reports = snapshot.data!;
          if (reports.isEmpty) {
            return StudentPageState(
              icon: Icons.flag_outlined,
              title: tr("还没有举报记录"),
              description: tr("如果讲解中有不合适的内容，可以通过消息菜单举报"),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
            itemCount: reports.length,
            itemBuilder: (context, index) {
              final item = reports[index] as Map<String, dynamic>;
              final reply = item['reply'] as String? ?? '';
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item['status'] == 'reviewed'
                            ? tr("已回复")
                            : item['status'] == 'dismissed'
                            ? tr("已处理")
                            : tr("处理中"),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.primary,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        tr("消息：{0}", [item['content'] ?? '']),
                        maxLines: 4,
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(tr("原因：{0}", [item['reason'] ?? ''])),
                      if (reply.isNotEmpty) ...[
                        const Divider(),
                        Text(tr("工作人员回复：{0}", [reply])),
                      ],
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
