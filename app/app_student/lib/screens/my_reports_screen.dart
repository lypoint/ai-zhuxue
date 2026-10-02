import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

class MyReportsScreen extends StatefulWidget {
  const MyReportsScreen({super.key});

  @override
  State<MyReportsScreen> createState() => _MyReportsScreenState();
}

class _MyReportsScreenState extends State<MyReportsScreen> {
  late Future<List<dynamic>> _reports = Api.I.myReports();

  void _reload() => setState(() => _reports = Api.I.myReports());

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('我的举报'),
      actions: [
        IconButton(
          tooltip: '刷新举报',
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
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('加载失败，请检查网络后重试'),
                TextButton(onPressed: _reload, child: const Text('重试')),
              ],
            ),
          );
        }
        final reports = snapshot.data!;
        if (reports.isEmpty) return const Center(child: Text('还没有举报记录'));
        return ListView.builder(
          itemCount: reports.length,
          itemBuilder: (context, index) {
            final item = reports[index] as Map<String, dynamic>;
            final reply = item['reply'] as String? ?? '';
            return Card(
              margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item['status'] == 'reviewed'
                          ? '已回复'
                          : item['status'] == 'dismissed'
                          ? '已处理'
                          : '处理中',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '消息：${item['content'] ?? ''}',
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text('原因：${item['reason'] ?? ''}'),
                    if (reply.isNotEmpty) ...[
                      const Divider(),
                      Text('工作人员回复：$reply'),
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
