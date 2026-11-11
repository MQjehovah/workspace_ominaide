import 'package:flutter/services.dart';

/// Result of reading the system clipboard.
class ClipboardPayload {
  const ClipboardPayload(
      {this.text = '', this.imageBytes, this.mimeType, this.name});

  final String text;
  final Uint8List? imageBytes;
  final String? mimeType;
  final String? name;

  bool get hasImage => imageBytes != null && imageBytes!.isNotEmpty;
  bool get isEmpty => text.trim().isEmpty && !hasImage;
}

/// Reads text and images from the system clipboard.
///
/// Flutter only exposes text through [Clipboard]; the image branch goes through
/// a small native channel so "copy a photo, paste it into 随手记" works.
class ClipboardService {
  static const _channel = MethodChannel('omniaide/clipboard');

  Future<ClipboardPayload> read() async {
    String text = '';
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      text = data?.text ?? '';
    } catch (_) {
      text = '';
    }
    Uint8List? bytes;
    String? mime;
    String? name;
    try {
      final result =
          await _channel.invokeMapMethod<String, dynamic>('readImage');
      if (result != null) {
        final raw = result['bytes'];
        if (raw is Uint8List && raw.isNotEmpty) {
          bytes = raw;
        } else if (raw is List<int> && raw.isNotEmpty) {
          bytes = Uint8List.fromList(raw);
        }
        final type = (result['mime'] ?? '').toString();
        if (type.isNotEmpty && bytes != null) mime = type;
        final fileName = (result['name'] ?? '').toString();
        if (fileName.isNotEmpty) name = fileName;
      }
    } on MissingPluginException {
      // Desktop/web builds may not implement the channel.
    } on PlatformException {
      // Clipboard access denied or empty.
    }
    return ClipboardPayload(
      text: text,
      imageBytes: bytes,
      mimeType: mime,
      name: name,
    );
  }
}
