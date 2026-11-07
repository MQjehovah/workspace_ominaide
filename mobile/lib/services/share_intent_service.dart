import 'dart:async';

import 'package:receive_sharing_intent/receive_sharing_intent.dart';

class SharedCapture {
  const SharedCapture({this.text, this.url, this.imagePath});
  final String? text;
  final String? url;
  final String? imagePath;
}

/// Receives links/images/text shared from other mobile apps.
class ShareIntentService {
  static final ShareIntentService _instance = ShareIntentService._();
  factory ShareIntentService() => _instance;
  ShareIntentService._();

  StreamSubscription<List<SharedMediaFile>>? _sub;
  SharedCapture? _pending;

  SharedCapture? takePending() {
    final value = _pending;
    _pending = null;
    return value;
  }

  Future<void> init() async {
    try {
      final initial = await ReceiveSharingIntent.instance.getInitialMedia();
      if (initial.isNotEmpty) {
        _handle(initial);
        ReceiveSharingIntent.instance.reset();
      }
      _sub = ReceiveSharingIntent.instance.getMediaStream().listen(_handle);
    } catch (_) {
      // Platform not configured (e.g. iOS share extension not installed).
    }
  }

  void _handle(List<SharedMediaFile> files) {
    if (files.isEmpty) return;
    String? text;
    String? url;
    String? image;
    for (final file in files) {
      if (file.type == SharedMediaType.url) {
        url = file.path;
      } else if (file.type == SharedMediaType.text) {
        text = file.path;
      } else if (file.type == SharedMediaType.image) {
        image = file.path;
      } else if (text == null) {
        text = file.path;
      }
    }
    _pending = SharedCapture(text: text, url: url, imagePath: image);
  }

  void dispose() {
    _sub?.cancel();
    _sub = null;
  }
}
