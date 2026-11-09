import 'dart:async';
import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class VideosScreen extends StatefulWidget {
  const VideosScreen({super.key});
  @override
  State<VideosScreen> createState() => _VideosScreenState();
}

class _VideosScreenState extends State<VideosScreen> {
  final _query = TextEditingController();
  Map<String, dynamic>? _results;
  String _searched = '';
  String? _error;
  bool _busy = false;
  int _request = 0;

  @override
  void dispose() {
    _request++;
    _query.dispose();
    super.dispose();
  }

  Future<void> _search([int page = 1]) async {
    final q = (page == 1 ? _query.text : _searched).trim();
    if (q.isEmpty) return;
    final task = ++_request;
    setState(() {
      _busy = true;
      _error = null;
      _results = null;
    });
    try {
      final data = await Api.I.searchVideos(q, page: page);
      if (mounted && task == _request) {
        setState(() {
          _results = data;
          _searched = q;
        });
      }
    } catch (e) {
      if (mounted && task == _request) {
        setState(
          () => _error = e is ApiException ? e.message : tr('视频加载失败，请重试'),
        );
      }
    } finally {
      if (mounted && task == _request) setState(() => _busy = false);
    }
  }

  Future<void> _play(String id) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await Api.I.videoPlayback(id);
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => _VideoPlayer(video: data)),
      );
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiException ? e.message : tr('视频加载失败，请重试'),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final items = _results?['items'] as List<dynamic>? ?? [];
    final page = _results?['page'] as int? ?? 1;
    return Scaffold(
      appBar: AppBar(title: Text(tr('讲解视频'))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(tr('搜索 B 站校园学习公开视频，使用播放器控制暂停、进度和全屏。')),
          const SizedBox(height: 16),
          TextField(
            controller: _query,
            maxLength: 100,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              labelText: tr('搜索知识点或课程'),
              border: const OutlineInputBorder(),
            ),
            onSubmitted: (_) {
              if (!_busy) _search();
            },
          ),
          FilledButton.icon(
            onPressed: _busy ? null : _search,
            icon: const Icon(Icons.search),
            label: Text(tr('搜索')),
          ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_error != null)
            Padding(padding: const EdgeInsets.all(12), child: Text(_error!)),
          if (_results != null && items.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(tr('没有找到相关讲解视频，请换个关键词')),
            ),
          for (final item in items)
            Card(
              child: ListTile(
                title: Text(item['title'] as String),
                subtitle: Text('${item['author']} · ${item['duration']}'),
                trailing: IconButton(
                  tooltip: tr('播放视频'),
                  icon: const Icon(Icons.play_circle_outline),
                  onPressed: _busy ? null : () => _play(item['id'] as String),
                ),
                onTap: _busy ? null : () => _play(item['id'] as String),
              ),
            ),
          if (_results != null)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton(
                  onPressed: _busy || page == 1
                      ? null
                      : () => _search(page - 1),
                  child: Text(tr('上一页')),
                ),
                Text('$page'),
                TextButton(
                  onPressed: _busy || _results!['has_more'] != true
                      ? null
                      : () => _search(page + 1),
                  child: Text(tr('下一页')),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _VideoPlayer extends StatefulWidget {
  const _VideoPlayer({required this.video});
  final Map<String, dynamic> video;
  @override
  State<_VideoPlayer> createState() => _VideoPlayerState();
}

class _VideoPlayerState extends State<_VideoPlayer>
    with WidgetsBindingObserver {
  late final WebViewController _controller;
  Timer? _timer;
  DateTime _since = DateTime.now();
  bool _checking = false;
  bool _stopped = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (request) {
            final uri = Uri.tryParse(request.url);
            return request.url == 'about:blank' ||
                    (uri?.scheme == 'https' &&
                        uri?.host == 'player.bilibili.com')
                ? NavigationDecision.navigate
                : NavigationDecision.prevent;
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true) _stop(tr('视频加载失败，请重试'));
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.video['embed_url'] as String));
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _pulse());
    _pulse();
  }

  Future<void> _pulse() async {
    if (_checking || _stopped) return;
    _checking = true;
    try {
      final seconds = DateTime.now().difference(_since).inSeconds.clamp(0, 120);
      _since = DateTime.now();
      if (seconds > 0) await Api.I.heartbeat(seconds);
      final status = await Api.I.chatAvailability();
      if (status['resting'] == true || status['remaining_seconds'] == 0) {
        _stop(tr('视频学习已暂停，请休息后再来'));
      }
    } catch (e) {
      _stop(e is ApiException ? e.message : tr('视频加载失败，请重试'));
    } finally {
      _checking = false;
    }
  }

  void _stop(String message) {
    if (!mounted || _stopped) return;
    _stopped = true;
    _timer?.cancel();
    unawaited(
      _controller.loadRequest(Uri.parse('about:blank')).catchError((_) {}),
    );
    setState(() => _error = message);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      _pulse();
      _stop(tr('视频学习已暂停，请休息后再来'));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    unawaited(
      _controller.loadRequest(Uri.parse('about:blank')).catchError((_) {}),
    );
    final seconds = DateTime.now().difference(_since).inSeconds.clamp(0, 120);
    if (seconds > 0 && !_stopped) {
      unawaited(Api.I.heartbeat(seconds).catchError((_) {}));
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.video['title'] as String)),
    body: Column(
      children: [
        if (_error != null)
          Padding(padding: const EdgeInsets.all(24), child: Text(_error!))
        else
          Expanded(child: WebViewWidget(controller: _controller)),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(tr('视频由第三方平台提供，无法播放时请重试或选择其他视频。')),
        ),
      ],
    ),
  );
}
