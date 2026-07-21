import 'dart:io';
import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import '../services/api_service.dart';
import '../models/file_item.dart';

class MusicScreen extends StatefulWidget {
  const MusicScreen({super.key});
  @override
  State<MusicScreen> createState() => _MusicScreenState();
}

class _MusicScreenState extends State<MusicScreen> {
  List<Map<String, dynamic>> _playlists = [];
  List<FileItem> _allTracks = [];
  List<Map<String, dynamic>> _currentSongs = [];
  Map<String, dynamic>? _currentPlaylist;
  bool _loading = true;
  bool _showAll = true;

  final _player = AudioPlayer();
  int? _playingIndex;
  bool _playing = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  @override
  void initState() {
    super.initState();
    _load();
    _player.onPositionChanged.listen((p) => setState(() => _position = p));
    _player.onDurationChanged.listen((d) => setState(() => _duration = d));
    _player.onPlayerComplete.listen((_) {
      if (!mounted) return;
      if (_playingIndex != null && _playingIndex! < _currentSongs.length - 1) {
        _playSong(_playingIndex! + 1);
      } else {
        setState(() { _playing = false; _position = Duration.zero; });
      }
    });
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = ApiService();
      _playlists = await api.listPlaylists();
      _allTracks = await api.listAudioFiles();
      if (_showAll) {
        _currentSongs = _allTracks.map((f) => {'file_id': f.id, 'name': f.originalName, 'size': f.size}).toList();
      }
    } catch (_) {}
    if (!mounted) return;
    setState(() => _loading = false);
  }

  Future<void> _openPlaylist(Map<String, dynamic> pl) async {
    final songs = await ApiService().listPlaylistSongs(pl['id']);
    if (!mounted) return;
    setState(() {
      _currentPlaylist = pl;
      _currentSongs = songs;
      _showAll = false;
    });
  }

  Future<void> _showAddSong(List<FileItem> tracks) async {
    final selected = <int>{};
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDlgState) => AlertDialog(
            title: const Text('选择要添加的歌曲'),
            content: SizedBox(
              width: double.maxFinite,
              height: 400,
              child: ListView.builder(
                itemCount: tracks.length,
                itemBuilder: (_, i) {
                  final t = tracks[i];
                  final inPlaylist = _currentSongs.any((s) => s['file_id'] == t.id);
                  return CheckboxListTile(
                    title: Text(t.originalName, style: const TextStyle(fontSize: 13)),
                    value: selected.contains(i) || inPlaylist,
                    onChanged: inPlaylist ? null : (v) {
                      if (v == true) setDlgState(() => selected.add(i));
                      else setDlgState(() => selected.remove(i));
                    },
                  );
                },
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
              TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('添加')),
            ],
          ),
        );
      },
    );
    if (result != true || _currentPlaylist == null) return;
    for (final i in selected) {
      try {
        await ApiService().addSongToPlaylist(_currentPlaylist!['id'], tracks[i].id);
      } catch (_) {}
    }
    await _openPlaylist(_currentPlaylist!);
  }

  Future<void> _playSong(int index) async {
    if (index < 0 || index >= _currentSongs.length) return;
    await _player.stop();
    final song = _currentSongs[index];
    setState(() { _playingIndex = index; _playing = false; _position = Duration.zero; });
    try {
      final bytes = await ApiService().downloadFile(song['file_id']);
      final temp = File('${Directory.systemTemp.path}/${song['name']}');
      await temp.writeAsBytes(bytes);
      await _player.play(DeviceFileSource(temp.path));
      setState(() => _playing = true);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('播放失败: $e')));
    }
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_currentPlaylist != null ? _currentPlaylist!['name'] : '音乐'),
        actions: [
          if (_currentPlaylist != null) ...[
            IconButton(icon: const Icon(Icons.library_music_outlined), onPressed: () => setState(() {
              _currentPlaylist = null;
              _showAll = true;
              _currentSongs = _allTracks.map((f) => {'file_id': f.id, 'name': f.originalName, 'size': f.size}).toList();
            }), tooltip: '全部歌曲'),
            IconButton(icon: const Icon(Icons.playlist_add), onPressed: () => _showAddSong(_allTracks)),
          ],
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _currentPlaylist == null && _showAll
          ? _buildPlaylistView()
          : _buildSongList(),
      bottomSheet: _playingIndex != null ? _buildPlayer() : null,
    );
  }

  Widget _buildPlaylistView() {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        itemCount: _playlists.length + 1,
        itemBuilder: (_, i) {
          if (i == 0) {
            return Column(
              children: [
                ListTile(
                  leading: const CircleAvatar(child: Icon(Icons.all_inclusive)),
                  title: const Text('全部歌曲', style: TextStyle(fontSize: 14)),
                  subtitle: Text('${_allTracks.length} 首', style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => setState(() {
                    _showAll = true;
                    _currentSongs = _allTracks.map((f) => {'file_id': f.id, 'name': f.originalName, 'size': f.size}).toList();
                  }),
                ),
                const Divider(),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    children: [
                      Text('我的歌单', style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
                      const Spacer(),
                      IconButton(icon: const Icon(Icons.add, size: 20), onPressed: _createPlaylist),
                    ],
                  ),
                ),
              ],
            );
          }
          final pl = _playlists[i - 1];
          return ListTile(
            leading: const CircleAvatar(child: Icon(Icons.queue_music, size: 20)),
            title: Text(pl['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text('${pl['song_count'] ?? 0} 首', style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, size: 18),
              onPressed: () async {
                await ApiService().deletePlaylist(pl['id']);
                _load();
              },
            ),
            onTap: () => _openPlaylist(pl),
          );
        },
      ),
    );
  }

  Future<void> _createPlaylist() async {
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final c = TextEditingController();
        return AlertDialog(
          title: const Text('新建歌单'),
          content: TextField(controller: c, autofocus: true, decoration: const InputDecoration(hintText: '歌单名称')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            TextButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('创建')),
          ],
        );
      },
    );
    if (name == null || name.isEmpty) return;
    try {
      await ApiService().createPlaylist(name);
      _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Widget _buildSongList() {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        itemCount: _currentSongs.length,
        itemBuilder: (_, i) {
          final s = _currentSongs[i];
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: _playingIndex == i ? Colors.blue : Colors.grey.shade200,
              child: Icon(_playingIndex == i ? Icons.play_arrow : Icons.music_note,
                color: _playingIndex == i ? Colors.white : Colors.grey.shade700, size: 20),
            ),
            title: Text(s['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text(_fmtSize(s['size'] ?? 0), style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
            trailing: _currentPlaylist != null
              ? IconButton(icon: const Icon(Icons.remove_circle_outline, size: 18),
                  onPressed: () async {
                    await ApiService().removeSongFromPlaylist(_currentPlaylist!['id'], s['item_id']);
                    _openPlaylist(_currentPlaylist!);
                  })
              : null,
            onTap: () => _playSong(i),
          );
        },
      ),
    );
  }

  Widget _buildPlayer() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_currentSongs[_playingIndex!]['name'] ?? '', style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Slider(
            value: _duration.inMilliseconds > 0 ? _position.inMilliseconds / _duration.inMilliseconds : 0,
            onChanged: (v) => _player.seek(Duration(milliseconds: (v * _duration.inMilliseconds).round())),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_fmt(_position), style: const TextStyle(fontSize: 11, color: Colors.grey)),
                Text(_fmt(_duration), style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(onPressed: _playingIndex! > 0 ? () => _playSong(_playingIndex! - 1) : null, icon: const Icon(Icons.skip_previous)),
              IconButton(onPressed: () {
                if (_playing) { _player.pause(); setState(() => _playing = false); }
                else { _player.resume(); setState(() => _playing = true); }
              }, icon: Icon(_playing ? Icons.pause_circle_filled : Icons.play_circle_filled, size: 48)),
              IconButton(onPressed: _playingIndex! < _currentSongs.length - 1 ? () => _playSong(_playingIndex! + 1) : null, icon: const Icon(Icons.skip_next)),
            ],
          ),
        ],
      ),
    );
  }

  String _fmtSize(dynamic bytes) {
    if (bytes is! num) return '';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
