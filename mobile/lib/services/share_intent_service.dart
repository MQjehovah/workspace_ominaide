import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
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

  static const MethodChannel _channel = MethodChannel('omniaide/share_intent');

  StreamSubscription<List<SharedMediaFile>>? _sub;
  SharedCapture? _pending;
  bool _ready = false;

  /// Called when a share arrives while the app is already running.
  void Function(SharedCapture capture)? onCapture;

  SharedCapture? takePending() {
    final value = _pending;
    _pending = null;
    return value;
  }

  /// Marks startup as finished so later shares navigate immediately.
  void markReady() {
    _ready = true;
    final pending = _pending;
    _pending = null;
    if (pending != null) {
      onCapture?.call(pending);
    }
  }

  Future<void> init() async {
    try {
      _sub = ReceiveSharingIntent.instance.getMediaStream().listen(_handle);
      final initial = await ReceiveSharingIntent.instance.getInitialMedia();
      if (initial.isNotEmpty) {
        _handle(initial);
        await ReceiveSharingIntent.instance.reset();
      }
      // Cold starts launched by the iOS share extension deliver the URL before
      // Dart is listening; SceneDelegate stashes it and we replay it now.
      final replay = Completer<void>();
      _replay = replay;
      final replayed = await _channel.invokeMethod<bool>('replayPendingUrl');
      debugPrint('[share] replayPendingUrl -> $replayed');
      if (replayed == true) {
        await replay.future.timeout(
          const Duration(milliseconds: 1500),
          onTimeout: () {},
        );
        if (!replay.isCompleted) {
          // The event channel was not attached in time; read the payload
          // written by the share extension directly.
          final raw = await _channel.invokeMethod<String>('takePendingShareJson');
          if (raw != null && raw.isNotEmpty) {
            final list = (jsonDecode(raw) as List)
                .map((item) => SharedMediaFile.fromMap(
                      Map<String, dynamic>.from(item as Map),
                    ))
                .toList();
            _handle(list);
          }
        }
      }
    } catch (_) {
      // Platform not configured (e.g. iOS share extension not installed).
    } finally {
      _replay = null;
    }
  }

  Completer<void>? _replay;

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
    final capture = SharedCapture(text: text, url: url, imagePath: image);
    debugPrint('[share] captured ${files.length} item(s) url=${url != null} text=${text != null} image=${image != null}');
    _pending = capture;
    _replay?.complete();
    if (_ready) {
      onCapture?.call(capture);
    }
  }

  void dispose() {
    _sub?.cancel();
    _sub = null;
  }
}
