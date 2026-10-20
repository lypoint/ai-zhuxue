import 'package:flutter/material.dart';
import 'api.dart';
import 'language.dart';

/// Resolve a short-lived private URL only after the API checks family ownership.
class MessageImages extends StatelessWidget {
  final List<dynamic> blocks;
  const MessageImages({super.key, required this.blocks});

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      for (final block in blocks)
        if (block is Map &&
            block['type'] == 'image' &&
            block['asset_id'] is String)
          _PrivateImage(
            key: ValueKey(block['asset_id']),
            assetId: block['asset_id'] as String,
            caption: block['caption'] as String? ?? '',
          ),
    ],
  );
}

class _PrivateImage extends StatefulWidget {
  final String assetId;
  final String caption;
  const _PrivateImage({
    super.key,
    required this.assetId,
    required this.caption,
  });

  @override
  State<_PrivateImage> createState() => _PrivateImageState();
}

class _PrivateImageState extends State<_PrivateImage> {
  late Future<Map<String, dynamic>> _image;

  @override
  void initState() {
    super.initState();
    _image = Api.I.mediaImage(widget.assetId);
  }

  void _retry() {
    setState(() {
      _image = Api.I.mediaImage(widget.assetId);
      _image.ignore(); // FutureBuilder attaches on the next frame; retain its error state.
    });
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(
    future: _image,
    builder: (context, snapshot) {
      if (snapshot.hasError) {
        return TextButton.icon(
          onPressed: _retry,
          icon: const Icon(Icons.refresh),
          label: Text(tr('图片加载失败，点击重试')),
        );
      }
      if (!snapshot.hasData) {
        return const Padding(
          padding: EdgeInsets.all(12),
          child: SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        );
      }
      final url = snapshot.data!['url'] as String;
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              label: widget.caption.isEmpty ? tr('题目图片') : widget.caption,
              button: true,
              child: InkWell(
                onTap: () => showDialog<void>(
                  context: context,
                  builder: (ctx) => Dialog(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Align(
                          alignment: Alignment.centerRight,
                          child: IconButton(
                            tooltip: tr('关闭'),
                            onPressed: () => Navigator.pop(ctx),
                            icon: const Icon(Icons.close),
                          ),
                        ),
                        Flexible(
                          child: InteractiveViewer(
                            minScale: .5,
                            maxScale: 6,
                            child: Image.network(
                              url,
                              errorBuilder: (_, error, stack) => TextButton(
                                onPressed: () {
                                  Navigator.pop(ctx);
                                  _retry();
                                },
                                child: Text(tr('图片加载失败，点击重试')),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.network(
                    url,
                    height: 220,
                    fit: BoxFit.contain,
                    errorBuilder: (_, error, stack) => TextButton(
                      onPressed: _retry,
                      child: Text(tr('图片加载失败，点击重试')),
                    ),
                  ),
                ),
              ),
            ),
            if (widget.caption.isNotEmpty)
              Text(
                widget.caption,
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
          ],
        ),
      );
    },
  );
}
