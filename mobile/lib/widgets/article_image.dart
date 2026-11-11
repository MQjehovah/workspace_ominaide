import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Full-width article image with a loading placeholder, a tap-to-zoom viewer
/// and automatic fallback to the CDN's original (non-negotiated) asset.
class ArticleImage extends StatefulWidget {
  const ArticleImage({super.key, required this.candidates, this.alt = ''});

  /// Candidate URLs in priority order. The next one is tried when a request
  /// fails to decode or load.
  final List<String> candidates;
  final String alt;

  @override
  State<ArticleImage> createState() => _ArticleImageState();
}

class _ArticleImageState extends State<ArticleImage> {
  int _index = 0;

  String get _url {
    final last = widget.candidates.length - 1;
    final index = _index.clamp(0, last);
    return widget.candidates[index];
  }

  void _retryNext() {
    if (_index + 1 >= widget.candidates.length) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _index += 1);
    });
  }

  void _openFullScreen() {
    showDialog<void>(
      context: context,
      barrierColor: Colors.black.withAlpha(235),
      builder: (context) => Dialog.fullscreen(
        backgroundColor: Colors.black,
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                minScale: 1,
                maxScale: 4,
                child: Center(
                  child: Image.network(
                    _url,
                    fit: BoxFit.contain,
                    errorBuilder: (context, error, stack) => const Icon(
                      Icons.broken_image_outlined,
                      color: Colors.white54,
                      size: 40,
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              top: 8,
              right: 8,
              child: IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close_rounded, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    if (widget.candidates.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: GestureDetector(
          onTap: _openFullScreen,
          child: Image.network(
            _url,
            key: ValueKey(_url),
            width: double.infinity,
            fit: BoxFit.fitWidth,
            filterQuality: FilterQuality.medium,
            semanticLabel: widget.alt.isEmpty ? null : widget.alt,
            headers: const {
              'Accept': 'image/jpeg,image/png,image/*;q=0.8',
            },
            loadingBuilder: (context, child, progress) {
              if (progress == null) return child;
              return AspectRatio(
                aspectRatio: 16 / 9,
                child: ColoredBox(
                  color: palette.line.withAlpha(70),
                  child: Center(
                    child: SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: palette.primary,
                      ),
                    ),
                  ),
                ),
              );
            },
            errorBuilder: (context, error, stack) {
              _retryNext();
              if (_index + 1 < widget.candidates.length) {
                return const AspectRatio(
                  aspectRatio: 16 / 9,
                  child: SizedBox.shrink(),
                );
              }
              return AspectRatio(
                aspectRatio: 16 / 9,
                child: ColoredBox(
                  color: palette.line.withAlpha(70),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.broken_image_outlined,
                        color: palette.muted,
                        size: 22,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '图片加载失败',
                        style: TextStyle(fontSize: 11, color: palette.muted),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
