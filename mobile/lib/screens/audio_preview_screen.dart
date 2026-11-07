import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import '../services/file_transfer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class AudioPreviewScreen extends StatefulWidget {
  const AudioPreviewScreen({
    super.key,
    required this.fileId,
    required this.filename,
  });

  final int fileId;
  final String filename;

  @override
  State<AudioPreviewScreen> createState() => _AudioPreviewScreenState();
}

class _AudioPreviewScreenState extends State<AudioPreviewScreen> {
  final _player = AudioPlayer();
  String _error = '';
  double _download = 0;
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  bool _loading = true;
  bool _playing = false;

  @override
  void initState() {
    super.initState();
    _player.onDurationChanged.listen((value) {
      if (mounted) setState(() => _duration = value);
    });
    _player.onPositionChanged.listen((value) {
      if (mounted) setState(() => _position = value);
    });
    _player.onPlayerComplete.listen((_) {
      if (mounted) {
        setState(() {
          _playing = false;
          _position = Duration.zero;
        });
      }
    });
    _open();
  }

  Future<void> _open() async {
    try {
      final file = await FileTransferService().download(
        widget.fileId,
        widget.filename,
        onProgress: (sent, total) {
          if (!mounted || total <= 0) return;
          setState(() => _download = sent / total);
        },
      );
      await _player.setSource(DeviceFileSource(file.path));
      if (!mounted) return;
      setState(() => _loading = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _toggle() async {
    if (_playing) {
      await _player.pause();
    } else {
      await _player.resume();
    }
    if (mounted) setState(() => _playing = !_playing);
  }

  String _fmt(Duration value) {
    final m = value.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = value.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final max = _duration.inMilliseconds.toDouble();
    final value = _position.inMilliseconds.clamp(0, max.toInt()).toDouble();
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Audio',
              title: widget.filename,
              subtitle: '应用内播放',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: _loading
                      ? Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            LinearProgressIndicator(
                              value: _download > 0 && _download < 1
                                  ? _download
                                  : null,
                              color: palette.primary,
                              backgroundColor: palette.primarySoft,
                            ),
                            const SizedBox(height: 10),
                            Text(
                              _download > 0 && _download < 1
                                  ? '下载 ${(_download * 100).toStringAsFixed(0)}%'
                                  : '准备播放…',
                              style: TextStyle(
                                fontSize: 11,
                                color: palette.muted,
                              ),
                            ),
                          ],
                        )
                      : _error.isNotEmpty
                          ? Text(
                              '播放失败：$_error',
                              style: TextStyle(
                                fontSize: 12,
                                color: palette.accent,
                              ),
                            )
                          : Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.graphic_eq_rounded,
                                  size: 80,
                                  color: palette.primary,
                                ),
                                const SizedBox(height: 16),
                                Slider(
                                  value: max <= 0 ? 0 : value.clamp(0, max),
                                  max: max <= 0 ? 1 : max,
                                  onChanged: (next) {
                                    _player.seek(
                                      Duration(milliseconds: next.round()),
                                    );
                                  },
                                ),
                                Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    Text(
                                      _fmt(_position),
                                      style: TextStyle(
                                        fontSize: 10,
                                        color: palette.muted,
                                      ),
                                    ),
                                    Text(
                                      _fmt(_duration),
                                      style: TextStyle(
                                        fontSize: 10,
                                        color: palette.muted,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                FilledButton.icon(
                                  onPressed: _toggle,
                                  icon: Icon(
                                    _playing
                                        ? Icons.pause_rounded
                                        : Icons.play_arrow_rounded,
                                  ),
                                  label: Text(_playing ? '暂停' : '播放'),
                                ),
                              ],
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
