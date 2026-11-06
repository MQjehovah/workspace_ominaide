import 'package:flutter/services.dart';

/// On-device OCR via the iOS Vision framework.
class OcrService {
  static const _channel = MethodChannel('omniaide/ocr');
  static final OcrService _instance = OcrService._();
  factory OcrService() => _instance;
  OcrService._();

  Future<String> recognize(String imagePath) async {
    try {
      final text = await _channel.invokeMethod<String>(
        'recognize',
        <String, dynamic>{'path': imagePath},
      );
      return text ?? '';
    } on MissingPluginException {
      throw Exception('当前平台暂不支持文字识别');
    } on PlatformException catch (e) {
      throw Exception(e.message ?? '文字识别失败');
    }
  }
}
