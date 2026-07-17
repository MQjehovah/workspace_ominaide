import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import '../services/api_service.dart';

class MusicScreen extends StatefulWidget {
  const MusicScreen({super.key});
  @override
  State<MusicScreen> createState() => _MusicScreenState();
}

class _MusicScreenState extends State<MusicScreen> {
  List<Map<String, dynamic>> _tracks = [];
  bool _loading = true;
  final _player = AudioPlayer();
  int? _currentId;
  bool _playing = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  @override
  void initState() {
    super.initState();
    _loadTracks();
    _player.onPositionChanged.listen((p) { if (mounted) setState(() => _position = p); });
    _player.onDurationChanged.listen((d) { if (mounted) setState(() => _duration = d); });
    _player.onPlayerComplete.listen((_) { if (mounted) setState(() { _playing = false; _currentId = null; }); });
    _player.onPlayerStateChanged.listen((s) { if (mounted) setState(() => _playing = s == PlayerState.playing); });
  }

  Future<void> _loadTracks() async {
    setState(() => _loading = true);
    try {
      final res = await ApiService().get('/files?page_size=200&mime_type=audio');
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        _tracks = List<Map<String, dynamic>>.from(data['files'] ?? []);
      }
    } catch (_) {}
    if (!mounted) return;
    setState(() => _loading = false);
  }

  Future<void> _play(int id, String url) async {
    if (_currentId == id && _playing) {
      await _player.pause();
    } else if (_currentId == id) {
      await _player.resume();
    } else {
      _currentId = id;
      await _player.stop();
      await _player.play(UrlSource(url));
    }
  }

  String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('音乐')),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _tracks.isEmpty
          ? const Center(child: Text('暂无音乐文件', style: TextStyle(color: Colors.grey)))
          : Column(
              children: [
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _loadTracks,
                    child: ListView.builder(
                      itemCount: _tracks.length,
                      itemBuilder: (_, i) {
                        final t = _tracks[i];
                        final name = t['original_name'] ?? '';
                        final id = t['id'] ?? 0;
                        final isCurrent = id == _currentId;
                        return ListTile(
                          leading: Icon(isCurrent && _playing ? Icons.music_note : Icons.music_note_outlined,
                            color: isCurrent ? Colors.blue : null),
                          title: Text(name, style: TextStyle(fontSize: 14, color: isCurrent ? Colors.blue : null)),
                          subtitle: t['size'] != null
                            ? Text('${(t['size'] / 1024 / 1024).toStringAsFixed(1)} MB', style: TextStyle(fontSize: 11, color: Colors.grey.shade500))
                            : null,
                          trailing: IconButton(
                            icon: Icon(isCurrent && _playing ? Icons.pause : Icons.play_arrow),
                            onPressed: () async {
                              try {
                                final dl = await ApiService().get('/files/$id/download-url');
                                if (dl.statusCode == 200) {
                                  final url = jsonDecode(dl.body)['download_url'] ?? '';
                                  if (url.isNotEmpty) _play(id, url);
                                }
                              } catch (_) {}
                            },
                          ),
                        );
                      },
                    ),
                  ),
                ),
                if (_currentId != null)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surface,
                      boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 8, offset: const Offset(0, -2))],
                    ),
                    child: Column(
                      children: [
                        Text(_tracks.firstWhere((t) => t['id'] == _currentId, orElse: () => {})['original_name'] ?? '',
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                        const SizedBox(height: 8),
                        Slider(
                          value: _duration.inMilliseconds > 0 ? _position.inMilliseconds / _duration.inMilliseconds : 0,
                          onChanged: (v) {
                            final pos = Duration(milliseconds: (v * _duration.inMilliseconds).round());
                            _player.seek(pos);
                          },
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(_formatDuration(_position), style: const TextStyle(fontSize: 11, color: Colors.grey)),
                              Text(_formatDuration(_duration), style: const TextStyle(fontSize: 11, color: Colors.grey)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}
