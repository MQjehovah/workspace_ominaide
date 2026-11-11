import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../services/api_service.dart';
import '../services/clipboard_service.dart';
import '../services/ocr_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Fast capture composer.
///
/// There is no "record type" step: type text (URLs can be pasted inline), or
/// attach a photo, video, recording or file. The backend analyses and
/// classifies everything afterwards.
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

class _CaptureAttachment {
  const _CaptureAttachment({
    required this.path,
    required this.name,
    required this.mime,
    required this.kind,
  });

  final String path;
  final String name;
  final String mime;
  final String kind; // image / video / audio / file

  bool get isImage => kind == 'image';
}

class _QuickCaptureScreenState extends State<QuickCaptureScreen> {
  static const _maxBytes = 25 * 1024 * 1024;

  final _text = TextEditingController();
  final _recorder = AudioRecorder();
  final List<_CaptureAttachment> _attachments = [];

  Timer? _timer;
  Duration _elapsed = Duration.zero;
  bool _recording = false;
  bool _saving = false;
  String? _recordingPath;

  @override
  void initState() {
    super.initState();
    if ((widget.initialText ?? '').isNotEmpty) {
      _text.text = widget.initialText!;
    }
    if ((widget.initialUrl ?? '').isNotEmpty) {
      // Links are plain text now; the analyser picks them up later.
      _text.text = _text.text.isEmpty
          ? widget.initialUrl!
          : '${_text.text}\n${widget.initialUrl!}';
    }
    if ((widget.initialImagePath ?? '').isNotEmpty) {
      _attachments.add(
        _CaptureAttachment(
          path: widget.initialImagePath!,
          name: widget.initialImagePath!.split('/').last,
          mime: _mimeFor(widget.initialImagePath!),
          kind: 'image',
        ),
      );
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _text.dispose();
    _recorder.dispose();
    super.dispose();
  }

  String _stamp() {
    final now = DateTime.now();
    return '${now.month.toString().padLeft(2, '0')}'
        '${now.day.toString().padLeft(2, '0')}_'
        '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
  }

  String _mimeFor(String path) {
    final ext = path.split('.').last.toLowerCase();
    switch (ext) {
      case 'jpg':
      case 'jpeg':
        return 'image/jpeg';
      case 'png':
        return 'image/png';
      case 'heic':
        return 'image/heic';
      case 'gif':
        return 'image/gif';
      case 'webp':
        return 'image/webp';
      case 'mp4':
        return 'video/mp4';
      case 'mov':
        return 'video/quicktime';
      case 'm4v':
        return 'video/x-m4v';
      case 'm4a':
        return 'audio/mp4';
      case 'mp3':
        return 'audio/mpeg';
      case 'wav':
        return 'audio/wav';
      case 'aac':
        return 'audio/aac';
      case 'pdf':
        return 'application/pdf';
      default:
        return 'application/octet-stream';
    }
  }

  String _kindForMime(String mime) {
    if (mime.startsWith('image/')) return 'image';
    if (mime.startsWith('video/')) return 'video';
    if (mime.startsWith('audio/')) return 'audio';
    return 'file';
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  void _addPath(String path, {String? name, String? mime}) {
    if (_attachments.length >= 9) {
      _toast('一次最多 9 个附件');
      return;
    }
    final resolved = mime ?? _mimeFor(path);
    setState(() {
      _attachments.add(
        _CaptureAttachment(
          path: path,
          name: name ?? path.split('/').last,
          mime: resolved,
          kind: _kindForMime(resolved),
        ),
      );
    });
  }

  Future<void> _pickFromGallery() async {
    try {
      final files = await ImagePicker().pickMultiImage();
      if (files.isEmpty) return;
      for (final file in files) {
        _addPath(file.path, name: file.name);
      }
      await _ocrFill(files);
    } catch (e) {
      _toast('选择图片失败：$e');
    }
  }

  Future<void> _takePhoto() async {
    try {
      final file = await ImagePicker().pickImage(source: ImageSource.camera);
      if (file == null) return;
      _addPath(file.path, name: file.name);
      await _ocrFill([file]);
    } catch (e) {
      _toast('拍照失败：$e');
    }
  }

  Future<void> _recordVideo() async {
    try {
      final file = await ImagePicker().pickVideo(
        source: ImageSource.camera,
        maxDuration: const Duration(minutes: 5),
      );
      if (file == null) return;
      _addPath(file.path, name: file.name, mime: 'video/mp4');
    } catch (e) {
      _toast('录像失败：$e');
    }
  }

  Future<void> _pickFiles() async {
    try {
      final result = await FilePicker.platform.pickFiles(allowMultiple: true);
      if (result == null) return;
      for (final file in result.files) {
        final path = file.path;
        if (path == null) continue;
        _addPath(path, name: file.name);
      }
    } catch (e) {
      _toast('选择文件失败：$e');
    }
  }

  Future<void> _paste() async {
    final payload = await ClipboardService().read();
    if (payload.isEmpty) {
      _toast('剪贴板里没有文字或图片');
      return;
    }
    if (payload.hasImage) {
      try {
        final dir = await getTemporaryDirectory();
        final mime = payload.mimeType ?? 'image/png';
        final ext = mime.split('/').last.replaceAll('jpeg', 'jpg');
        final path =
            '${dir.path}/paste_${DateTime.now().millisecondsSinceEpoch}.$ext';
        await File(path).writeAsBytes(payload.imageBytes!);
        if (!mounted) return;
        _addPath(path, name: payload.name ?? '粘贴的图片.$ext', mime: mime);
      } catch (e) {
        _toast('粘贴图片失败：$e');
      }
    }
    final text = payload.text;
    if (text.isEmpty) return;
    final value = _text.value;
    final selection = value.selection;
    if (selection.isValid) {
      final next = value.text.replaceRange(
        selection.start,
        selection.end,
        text,
      );
      _text.value = TextEditingValue(
        text: next,
        selection: TextSelection.collapsed(
          offset: selection.start + text.length,
        ),
      );
    } else {
      _text.text = value.text.isEmpty ? text : '${value.text}$text';
    }
  }

  Future<void> _toggleRecording() async {
    if (_recording) {
      await _stopRecording();
      return;
    }
    try {
      if (!await _recorder.hasPermission()) {
        _toast('需要麦克风权限才能录音');
        return;
      }
      final dir = await getTemporaryDirectory();
      final path =
          '${dir.path}/capture_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc),
        path: path,
      );
      if (!mounted) return;
      setState(() {
        _recording = true;
        _elapsed = Duration.zero;
        _recordingPath = path;
      });
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted && _recording) {
          setState(() => _elapsed += const Duration(seconds: 1));
        }
      });
    } catch (e) {
      _toast('录音失败：$e');
    }
  }

  Future<void> _stopRecording() async {
    if (!_recording) return;
    _timer?.cancel();
    String? path;
    try {
      path = await _recorder.stop();
    } catch (_) {
      path = _recordingPath;
    }
    if (!mounted) return;
    setState(() {
      _recording = false;
      _recordingPath = null;
    });
    if (path == null) {
      _toast('没有录到声音');
      return;
    }
    _addPath(path, name: '录音_${_stamp()}.m4a', mime: 'audio/mp4');
  }

  Future<void> _ocrFill(List<XFile> files) async {
    if (_text.text.trim().isNotEmpty) return;
    for (final file in files) {
      final lower = file.path.toLowerCase();
      if (!lower.endsWith('.png') &&
          !lower.endsWith('.jpg') &&
          !lower.endsWith('.jpeg')) {
        continue;
      }
      try {
        final text = await OcrService().recognize(file.path);
        if (text.trim().isNotEmpty && mounted && _text.text.trim().isEmpty) {
          setState(() => _text.text = text.trim());
          return;
        }
      } catch (_) {
        // OCR is optional (iOS only today).
      }
    }
  }

  Future<void> _save() async {
    if (_saving) return;
    if (_recording) await _stopRecording();
    final text = _text.text.trim();
    if (_attachments.isEmpty && text.isEmpty) {
      _toast('写点什么，或加张照片/录音');
      return;
    }
    setState(() => _saving = true);
    var created = 0;
    var textUsed = false;
    try {
      if (_attachments.isEmpty) {
        await ApiService().createCapture(
          kind: 'text',
          text: text,
          source: 'mobile',
        );
        created = 1;
      } else {
        for (final attachment in _attachments) {
          final body = textUsed ? '' : text;
          final file = File(attachment.path);
          final size = await file.length();
          if (size > _maxBytes) {
            throw Exception('${attachment.name} 超过 25MB');
          }
          final bytes = await file.readAsBytes();
          await ApiService().uploadCapture(
            bytes,
            attachment.name,
            text: body,
            mimeType: attachment.mime,
            source: 'mobile',
          );
          textUsed = true;
          created++;
        }
      }
      if (!mounted) return;
      _toast(created > 1 ? '已收进随手记 $created 条，稍后分析' : '已收进随手记，稍后分析');
      Navigator.pop(context, true);
    } catch (e) {
      _toast('保存失败：${e.toString().replaceFirst('Exception: ', '')}');
    } finally {
      if (mounted) setState(() => _saving = false);
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
              kicker: 'Capture',
              title: '随手记',
              subtitle: '文字、照片、录像、录音，收进来就行',
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
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        TextField(
                          controller: _text,
                          autofocus: true,
                          minLines: 4,
                          maxLines: 10,
                          style: TextStyle(
                            fontSize: 15,
                            height: 1.6,
                            color: palette.ink,
                          ),
                          decoration: InputDecoration(
                            hintText: '想到什么就写下来，也可以直接粘贴…',
                            hintStyle: TextStyle(
                              fontSize: 14,
                              color: palette.muted,
                            ),
                            border: InputBorder.none,
                          ),
                        ),
                        if (_recording) ...[
                          const SizedBox(height: 6),
                          _recordingBar(palette),
                        ],
                        if (_attachments.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (var i = 0; i < _attachments.length; i++)
                                _attachmentChip(palette, i),
                            ],
                          ),
                        ],
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                '支持粘贴文字或图片',
                                style: TextStyle(
                                  fontSize: 10.5,
                                  color: palette.muted,
                                ),
                              ),
                            ),
                            TextButton.icon(
                              onPressed: _paste,
                              style: TextButton.styleFrom(
                                visualDensity: VisualDensity.compact,
                                foregroundColor: palette.primary,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 8),
                              ),
                              icon: const Icon(
                                Icons.content_paste_rounded,
                                size: 14,
                              ),
                              label: const Text(
                                '粘贴',
                                style: TextStyle(fontSize: 11.5),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _bigAction(
                          palette,
                          Icons.photo_camera_rounded,
                          '拍照',
                          _takePhoto,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _bigAction(
                          palette,
                          Icons.videocam_rounded,
                          '录像',
                          _recordVideo,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _bigAction(
                          palette,
                          _recording ? Icons.stop_rounded : Icons.mic_rounded,
                          _recording ? '停止' : '录音',
                          _toggleRecording,
                          recording: _recording,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      _smallAction(
                        palette,
                        Icons.photo_library_outlined,
                        '相册',
                        _pickFromGallery,
                      ),
                      _smallAction(
                        palette,
                        Icons.attach_file_rounded,
                        '文件',
                        _pickFiles,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: _saving ? null : _save,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(46),
                    ),
                    icon: _saving
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.inbox_rounded),
                    label: Text(_saving ? '保存中…' : '收进随手记'),
                  ),
                  const SizedBox(height: 8),
                  Center(
                    child: Text(
                      '不用先选类型；文字里可以直接贴链接，保存后自动分析归类',
                      style: TextStyle(fontSize: 10.5, color: palette.muted),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _recordingBar(AppPalette palette) {
    final minutes = _elapsed.inMinutes.toString().padLeft(2, '0');
    final seconds = _elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: palette.accent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: palette.accent.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration:
                BoxDecoration(color: palette.accent, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '正在录音  $minutes:$seconds',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: palette.accent,
              ),
            ),
          ),
          TextButton(onPressed: _stopRecording, child: const Text('停止')),
        ],
      ),
    );
  }

  Widget _bigAction(
    AppPalette palette,
    IconData icon,
    String label,
    Future<void> Function() onTap, {
    bool recording = false,
  }) {
    final color = recording ? palette.accent : palette.primary;
    return Material(
      color: color,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: SizedBox(
          height: 52,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 20, color: Colors.white),
              const SizedBox(height: 3),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _smallAction(
    AppPalette palette,
    IconData icon,
    String label,
    Future<void> Function() onTap,
  ) {
    return Expanded(
      child: TextButton.icon(
        onPressed: onTap,
        style: TextButton.styleFrom(
          foregroundColor: palette.muted,
          padding: const EdgeInsets.symmetric(vertical: 8),
          visualDensity: VisualDensity.compact,
        ),
        icon: Icon(icon, size: 15),
        label: Text(
          label,
          style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500),
        ),
      ),
    );
  }

  Widget _attachmentChip(AppPalette palette, int index) {
    final attachment = _attachments[index];
    final icon = switch (attachment.kind) {
      'image' => Icons.image_outlined,
      'video' => Icons.videocam_outlined,
      'audio' => Icons.graphic_eq_rounded,
      _ => Icons.insert_drive_file_outlined,
    };
    return Container(
      constraints: const BoxConstraints(maxWidth: 220),
      padding: const EdgeInsets.fromLTRB(8, 5, 4, 5),
      decoration: BoxDecoration(
        color: palette.primarySoft,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (attachment.isImage)
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.file(
                File(attachment.path),
                width: 26,
                height: 26,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    Icon(icon, size: 15, color: palette.primary),
              ),
            )
          else
            Icon(icon, size: 15, color: palette.primary),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              attachment.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: palette.primary,
              ),
            ),
          ),
          IconButton(
            onPressed: () => setState(() => _attachments.removeAt(index)),
            icon: Icon(Icons.close_rounded, size: 14, color: palette.primary),
            visualDensity: VisualDensity.compact,
            constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
            padding: EdgeInsets.zero,
            tooltip: '移除',
          ),
        ],
      ),
    );
  }
}
