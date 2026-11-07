import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../services/file_transfer_service.dart';
import '../services/ocr_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Take a photo or pick an image, run OCR, then save as a note or upload it
/// to the OmniAide file library.
class PhotoScanScreen extends StatefulWidget {
  const PhotoScanScreen({super.key, required this.onOpenNote});

  final void Function(int noteId, String title) onOpenNote;

  @override
  State<PhotoScanScreen> createState() => _PhotoScanScreenState();
}

class _PhotoScanScreenState extends State<PhotoScanScreen> {
  final _text = TextEditingController();
  File? _image;
  bool _ocrRunning = false;
  bool _saving = false;
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _text.addListener(_refresh);
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _text.removeListener(_refresh);
    _text.dispose();
    super.dispose();
  }

  Future<void> _pick(ImageSource source) async {
    try {
      final picked = await ImagePicker().pickImage(
        source: source,
        imageQuality: 92,
        maxWidth: 2400,
      );
      if (picked == null || !mounted) return;
      setState(() {
        _image = File(picked.path);
        _text.clear();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('选择图片失败: $e')),
      );
    }
  }

  Future<void> _recognize() async {
    final image = _image;
    if (image == null || _ocrRunning) return;
    setState(() => _ocrRunning = true);
    try {
      final text = await OcrService().recognize(image.path);
      if (!mounted) return;
      setState(() => _text.text = text);
      if (text.trim().isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('没有识别到文字，可以重新拍一张')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _ocrRunning = false);
    }
  }

  String _stamp() {
    final now = DateTime.now();
    return '${now.year}${now.month.toString().padLeft(2, '0')}'
        '${now.day.toString().padLeft(2, '0')}_'
        '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
  }

  Future<void> _saveNote() async {
    final text = _text.text.trim();
    if (text.isEmpty || _saving) return;
    setState(() => _saving = true);
    try {
      final res = await ApiService().post('/plugins/notes', {
        'title': '扫描笔记 ${_stamp()}',
        'content': text,
      });
      if (res.statusCode != 201 && res.statusCode != 200) {
        throw Exception('保存失败: ${res.statusCode}');
      }
      final data = ApiService().decodeJson(res);
      final id = (data['id'] as num?)?.toInt();
      final title = (data['title'] ?? '扫描笔记').toString();
      if (!mounted) return;
      Navigator.pop(context);
      if (id != null) widget.onOpenNote(id, title);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _uploadImage() async {
    final image = _image;
    if (image == null || _uploading) return;
    setState(() => _uploading = true);
    final progress = ValueNotifier<double?>(null);
    final dialog = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        title: const Text('正在上传原图'),
        content: ValueListenableBuilder<double?>(
          valueListenable: progress,
          builder: (_, value, __) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              LinearProgressIndicator(value: value),
              const SizedBox(height: 10),
              Text(
                value == null
                    ? '准备中…'
                    : '${(value * 100).clamp(0, 100).toStringAsFixed(0)}%',
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
    try {
      final name = image.uri.pathSegments.last;
      await FileTransferService().upload(
        image.path,
        name.isEmpty ? 'scan.jpg' : name,
        '/',
        onProgress: (sent, total) {
          if (total > 0) progress.value = sent / total;
        },
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('原图已上传到文件')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('上传失败: $e')),
      );
    } finally {
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
      await dialog;
      WidgetsBinding.instance.addPostFrameCallback((_) => progress.dispose());
      if (mounted) setState(() => _uploading = false);
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
              kicker: 'Scan',
              title: '拍照扫描',
              subtitle: '识别文字后保存为笔记，或上传原图',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: [
                  if (_image == null)
                    AppCard(
                      child: Column(
                        children: [
                          Icon(Icons.document_scanner_outlined,
                              size: 46, color: palette.primary),
                          const SizedBox(height: 10),
                          Text(
                            '拍一张纸、白板或发票',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '会使用设备端 OCR 识别文字，图片不会上传到第三方。',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 11,
                              height: 1.5,
                              color: palette.muted,
                            ),
                          ),
                          const SizedBox(height: 18),
                          Row(
                            children: [
                              Expanded(
                                child: FilledButton.icon(
                                  onPressed: () => _pick(ImageSource.camera),
                                  icon: const Icon(Icons.photo_camera_outlined, size: 18),
                                  label: const Text('拍照'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: OutlinedButton.icon(
                                  onPressed: () => _pick(ImageSource.gallery),
                                  icon: const Icon(Icons.photo_library_outlined, size: 18),
                                  label: const Text('相册'),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    )
                  else ...[
                    AppCard(
                      padding: const EdgeInsets.all(8),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.file(
                          _image!,
                          height: 280,
                          width: double.infinity,
                          fit: BoxFit.contain,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () => _pick(ImageSource.camera),
                            icon: const Icon(Icons.photo_camera_outlined, size: 16),
                            label: const Text('重拍'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () => _pick(ImageSource.gallery),
                            icon: const Icon(Icons.photo_library_outlined, size: 16),
                            label: const Text('相册'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: FilledButton.icon(
                            onPressed: _ocrRunning ? null : _recognize,
                            icon: _ocrRunning
                                ? const SizedBox(
                                    width: 14,
                                    height: 14,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Icon(Icons.text_snippet_outlined, size: 16),
                            label: const Text('识别'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    AppCard(
                      child: TextField(
                        controller: _text,
                        minLines: 6,
                        maxLines: 14,
                        decoration: const InputDecoration(
                          hintText: '识别结果会显示在这里，可以直接修改',
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      height: 46,
                      child: FilledButton.icon(
                        onPressed: _saving || _text.text.trim().isEmpty
                            ? null
                            : _saveNote,
                        icon: _saving
                            ? const SizedBox(
                                width: 15,
                                height: 15,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.note_add_outlined, size: 18),
                        label: const Text('保存为笔记'),
                      ),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _uploading ? null : _uploadImage,
                      icon: const Icon(Icons.cloud_upload_outlined, size: 18),
                      label: const Text('上传原图到文件'),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
