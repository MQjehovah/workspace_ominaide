import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class QuickCaptureScreen extends StatefulWidget {
  const QuickCaptureScreen({
    super.key,
    this.initialText,
    this.initialUrl,
    this.initialImagePath,
  });

  final String? initialText;
  final String? initialUrl;
  final String? initialImagePath;

  @override
  State<QuickCaptureScreen> createState() => _QuickCaptureScreenState();
}

class _QuickCaptureScreenState extends State<QuickCaptureScreen> {
  final _title = TextEditingController();
  final _text = TextEditingController();
  final _url = TextEditingController();
  String _mode = 'text';
  XFile? _image;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if ((widget.initialUrl ?? '').isNotEmpty) {
      _mode = 'link';
      _url.text = widget.initialUrl!;
    }
    if ((widget.initialText ?? '').isNotEmpty) {
      _text.text = widget.initialText!;
    }
    if ((widget.initialImagePath ?? '').isNotEmpty) {
      _mode = 'image';
      _image = XFile(widget.initialImagePath!);
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _text.dispose();
    _url.dispose();
    super.dispose();
  }

  Future<void> _pickImage() async {
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery);
    if (picked != null) setState(() => _image = picked);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      if (_mode == 'image') {
        final file = _image;
        if (file == null) {
          _toast('请先选择图片');
          return;
        }
        final bytes = await file.readAsBytes();
        await ApiService().uploadCapture(
          bytes,
          file.name,
          text: _text.text.trim(),
          title: _title.text.trim(),
        );
      } else if (_mode == 'link') {
        final url = _url.text.trim();
        if (url.isEmpty) {
          _toast('请填写链接');
          return;
        }
        await ApiService().createCapture(
          kind: 'link',
          url: url,
          text: _text.text.trim(),
          title: _title.text.trim(),
        );
      } else {
        final text = _text.text.trim();
        if (text.isEmpty) {
          _toast('请填写内容');
          return;
        }
        await ApiService().createCapture(
          kind: 'text',
          text: text,
          title: _title.text.trim(),
        );
      }
      if (!mounted) return;
      _toast('已收进随手记，正在分析');
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) _toast('保存失败：$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _toast(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
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
              kicker: 'Capture',
              title: '随手记',
              subtitle: '先收进来，稍后分析',
              actions: [
                RoundIconButton(
                  icon: Icons.close_rounded,
                  onTap: () => Navigator.pop(context),
                ),
              ],
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: [
                  AppCard(
                    child: Column(
                      children: [
                        SegmentedButton<String>(
                          segments: const [
                            ButtonSegment(value: 'text', label: Text('文本'), icon: Icon(Icons.notes_rounded)),
                            ButtonSegment(value: 'link', label: Text('链接'), icon: Icon(Icons.link_rounded)),
                            ButtonSegment(value: 'image', label: Text('图片'), icon: Icon(Icons.image_rounded)),
                          ],
                          selected: {_mode},
                          onSelectionChanged: (v) => setState(() => _mode = v.first),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _title,
                          decoration: const InputDecoration(labelText: '标题（可选）'),
                        ),
                        if (_mode == 'link') ...[
                          const SizedBox(height: 10),
                          TextField(
                            controller: _url,
                            keyboardType: TextInputType.url,
                            decoration: const InputDecoration(labelText: '链接 URL'),
                          ),
                        ],
                        const SizedBox(height: 10),
                        if (_mode == 'image')
                          OutlinedButton.icon(
                            onPressed: _pickImage,
                            icon: const Icon(Icons.photo_library_outlined),
                            label: Text(_image?.name ?? '选择图片'),
                          ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _text,
                          minLines: 5,
                          maxLines: 12,
                          decoration: InputDecoration(
                            labelText: _mode == 'image' ? '图片说明（可选）' : '内容',
                            alignLabelWithHint: true,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _saving ? null : _save,
                    icon: _saving
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.save_rounded),
                    label: Text(_saving ? '保存中…' : '保存并分析'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
