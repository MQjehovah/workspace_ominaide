import 'package:flutter/material.dart';
import 'package:pdfx/pdfx.dart';

import '../services/file_transfer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// In-app PDF reader. Downloads through the authenticated file pipeline, then
/// renders with PDFKit/Android PDF instead of handing the URL to a browser.
class PdfPreviewScreen extends StatefulWidget {
  const PdfPreviewScreen({
    super.key,
    required this.fileId,
    required this.filename,
  });

  final int fileId;
  final String filename;

  @override
  State<PdfPreviewScreen> createState() => _PdfPreviewScreenState();
}

class _PdfPreviewScreenState extends State<PdfPreviewScreen> {
  PdfControllerPinch? _controller;
  String _error = '';
  double _progress = 0;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _open();
  }

  Future<void> _open() async {
    try {
      final file = await FileTransferService().download(
        widget.fileId,
        widget.filename,
        onProgress: (sent, total) {
          if (!mounted || total <= 0) return;
          setState(() => _progress = sent / total);
        },
      );
      final document = await PdfDocument.openFile(file.path);
      if (!mounted) return;
      setState(() {
        _controller = PdfControllerPinch(document: Future.value(document));
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'PDF',
              title: widget.filename,
              subtitle: '应用内预览',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(30),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            LinearProgressIndicator(
                              value: _progress > 0 && _progress < 1
                                  ? _progress
                                  : null,
                              color: palette.primary,
                              backgroundColor: palette.primarySoft,
                            ),
                            const SizedBox(height: 10),
                            Text(
                              _progress > 0 && _progress < 1
                                  ? '下载 ${(_progress * 100).toStringAsFixed(0)}%'
                                  : '正在打开 PDF…',
                              style: TextStyle(
                                fontSize: 11,
                                color: palette.muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                  : _error.isNotEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Text(
                              'PDF 预览失败：$_error',
                              style: TextStyle(
                                fontSize: 12,
                                color: palette.accent,
                              ),
                            ),
                          ),
                        )
                      : PdfViewPinch(
                          controller: _controller!,
                          backgroundDecoration: BoxDecoration(
                            color: palette.background,
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}
