import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class TextPreviewScreen extends StatefulWidget {
  const TextPreviewScreen({
    super.key,
    required this.fileId,
    required this.filename,
  });

  final int fileId;
  final String filename;

  @override
  State<TextPreviewScreen> createState() => _TextPreviewScreenState();
}

class _TextPreviewScreenState extends State<TextPreviewScreen> {
  String _text = '';
  String _error = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final bytes = await ApiService().downloadFile(widget.fileId);
      if (!mounted) return;
      setState(() {
        _text = utf8.decode(bytes, allowMalformed: true);
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
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Text',
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
                  ? const Center(child: CircularProgressIndicator())
                  : _error.isNotEmpty
                      ? Center(
                          child: Text(
                            '预览失败：$_error',
                            style: TextStyle(
                              fontSize: 12,
                              color: palette.accent,
                            ),
                          ),
                        )
                      : SingleChildScrollView(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                          child: AppCard(
                            child: SelectableText(
                              _text.isEmpty ? '（空文件）' : _text,
                              style: TextStyle(
                                fontSize: 13,
                                height: 1.7,
                                color: palette.ink,
                              ),
                            ),
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}
