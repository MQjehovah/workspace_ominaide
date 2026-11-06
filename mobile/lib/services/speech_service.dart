import 'package:speech_to_text/speech_to_text.dart' as stt;

/// Thin wrapper around on-device speech recognition.
///
/// Kept separate from the chat screen so platform failures (no mic, no
/// permission, unsupported browser) are easy to surface as a single error.
class SpeechService {
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _initialized = false;

  bool get isListening => _speech.isListening;

  Future<bool> initialize({
    void Function(String status)? onStatus,
    void Function(String message)? onError,
  }) async {
    if (_initialized) return true;
    try {
      _initialized = await _speech.initialize(
        onStatus: (status) => onStatus?.call(status),
        onError: (error) => onError?.call(error.errorMsg),
      );
      return _initialized;
    } catch (_) {
      return false;
    }
  }

  Future<String?> preferredLocale() async {
    try {
      final locales = await _speech.locales();
      for (final locale in locales) {
        final id = locale.localeId.toLowerCase();
        if (id.startsWith('zh') || id.contains('cmn')) {
          return locale.localeId;
        }
      }
    } catch (_) {}
    return null;
  }

  Future<void> start({
    required void Function(String text, bool isFinal) onResult,
    String? localeId,
  }) async {
    await _speech.listen(
      onResult: (result) => onResult(result.recognizedWords, result.finalResult),
      localeId: localeId,
      listenFor: const Duration(seconds: 60),
      pauseFor: const Duration(seconds: 3),
      partialResults: true,
      cancelOnError: true,
      listenMode: stt.ListenMode.dictation,
    );
  }

  Future<void> stop() async {
    try {
      await _speech.stop();
    } catch (_) {}
  }

  Future<void> cancel() async {
    try {
      await _speech.cancel();
    } catch (_) {}
  }
}

final speechService = SpeechService();
