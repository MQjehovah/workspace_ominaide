import 'package:flutter/material.dart';

import '../models/file_item.dart';
import '../services/api_service.dart';
import '../services/music_cache.dart';
import '../services/music_player_service.dart';

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

  final _player = MusicPlayerService();

  bool _downloading = false;
  String _downloadStatus = '';

  @override
  void initState() {
    super.initState();
    _player.initialize();
    _player.addListener(_onPlayerChanged);
    _load();
  }

  @override
  void dispose() {
    // Playback is app-wide; only stop listening to it.
    _player.removeListener(_onPlayerChanged);
    super.dispose();
  }

  void _onPlayerChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = ApiService();
      _playlists = await api.listPlaylists();
      _allTracks = await api.listAudioFiles();
      if (_showAll) {
        _currentSongs = _allTracks
            .map((f) => {
                  'file_id': f.id,
                  'name': f.originalName,
                  'size': f.size,
                })
            .toList();
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

  Future<void> _start(
    List<Map<String, dynamic>> songs,
    int index,
  ) async {
    try {
      await _player.playQueue(songs, index);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('播放失败: $e')),
      );
    }
  }

  Future<void> _playPlaylist(Map<String, dynamic> playlist) async {
    try {
      final songs = await ApiService().listPlaylistSongs(playlist['id']);
      if (!mounted) return;
      setState(() {
        _currentPlaylist = playlist;
        _currentSongs = songs;
        _showAll = false;
      });
      await _start(songs, 0);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('播放失败: $e')),
      );
    }
  }

  Future<void> _playAllTracks() async {
    final songs = _allTracks
        .map((file) => {
              'file_id': file.id,
              'name': file.originalName,
              'size': file.size,
            })
        .toList();
    if (!mounted) return;
    setState(() {
      _currentPlaylist = null;
      _showAll = true;
      _currentSongs = songs;
    });
    await _start(songs, 0);
  }

  void _showAllTracks() {
    setState(() {
      _showAll = true;
      _currentPlaylist = null;
      _currentSongs = _allTracks
          .map((f) => {
                'file_id': f.id,
                'name': f.originalName,
                'size': f.size,
              })
          .toList();
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
                  final inPlaylist =
                      _currentSongs.any((s) => s['file_id'] == t.id);
                  return CheckboxListTile(
                    title: Text(
                      t.originalName,
                      style: const TextStyle(fontSize: 13),
                    ),
                    value: selected.contains(i) || inPlaylist,
                    onChanged: inPlaylist
                        ? null
                        : (v) {
                            if (v == true) {
                              setDlgState(() => selected.add(i));
                            } else {
                              setDlgState(() => selected.remove(i));
                            }
                          },
                  );
                },
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('添加'),
              ),
            ],
          ),
        );
      },
    );
    if (result != true || _currentPlaylist == null) return;
    for (final i in selected) {
      try {
        await ApiService()
            .addSongToPlaylist(_currentPlaylist!['id'], tracks[i].id);
      } catch (_) {}
    }
    await _openPlaylist(_currentPlaylist!);
  }

  Future<void> _downloadSongs(
    List<Map<String, dynamic>> songs,
    String label,
  ) async {
    if (_downloading || songs.isEmpty) return;
    setState(() {
      _downloading = true;
      _downloadStatus = '0/${songs.length}';
    });
    var ok = 0;
    var failed = 0;
    for (var i = 0; i < songs.length; i++) {
      final id = (songs[i]['file_id'] as num?)?.toInt();
      if (id != null) {
        try {
          await MusicCache().cacheTrack(
            id,
            (songs[i]['name'] ?? 'track.mp3').toString(),
          );
          ok++;
        } catch (_) {
          failed++;
        }
      }
      if (mounted) {
        setState(() => _downloadStatus = '${i + 1}/${songs.length}');
      }
    }
    if (!mounted) return;
    setState(() {
      _downloading = false;
      _downloadStatus = '';
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          failed == 0 ? '「$label」已缓存 $ok 首' : '「$label」已缓存 $ok 首，$failed 首失败',
        ),
      ),
    );
  }

  Future<void> _downloadPlaylist(Map<String, dynamic> playlist) async {
    try {
      final songs = await ApiService().listPlaylistSongs(playlist['id']);
      if (!mounted) return;
      final normalized = songs
          .map((s) => {
                'file_id': s['file_id'],
                'name': s['name'] ?? s['title'] ?? 'track.mp3',
              })
          .toList();
      await _downloadSongs(normalized, (playlist['name'] ?? '歌单').toString());
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('读取歌单失败: $e')),
      );
    }
  }

  Future<void> _downloadCurrent() async {
    if (_currentPlaylist != null) {
      await _downloadPlaylist(_currentPlaylist!);
      return;
    }
    await _downloadSongs(
      _allTracks.map((f) => {'file_id': f.id, 'name': f.originalName}).toList(),
      '全部歌曲',
    );
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  IconData _modeIcon(MusicPlayMode mode) {
    switch (mode) {
      case MusicPlayMode.sequential:
        return Icons.playlist_play_rounded;
      case MusicPlayMode.repeatAll:
        return Icons.repeat_rounded;
      case MusicPlayMode.repeatOne:
        return Icons.repeat_one_rounded;
      case MusicPlayMode.shuffle:
        return Icons.shuffle_rounded;
    }
  }

  void _cycleMode() {
    _player.cycleMode();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        duration: const Duration(milliseconds: 900),
        content: Text(_player.modeLabel),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          _currentPlaylist != null
              ? (_currentPlaylist!['name'] ?? '音乐').toString()
              : '音乐',
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.download_outlined),
            onPressed: _downloading ? null : _downloadCurrent,
            tooltip: _currentPlaylist != null ? '缓存整个歌单' : '缓存全部歌曲',
          ),
          if (_currentPlaylist != null) ...[
            IconButton(
              icon: const Icon(Icons.library_music_outlined),
              onPressed: _showAllTracks,
              tooltip: '全部歌曲',
            ),
            IconButton(
              icon: const Icon(Icons.playlist_add),
              onPressed: () => _showAddSong(_allTracks),
            ),
          ],
        ],
      ),
      body: Column(
        children: [
          if (_downloading) ...[
            const LinearProgressIndicator(minHeight: 2),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Row(
                children: [
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '正在缓存 $_downloadStatus',
                    style: const TextStyle(fontSize: 11),
                  ),
                ],
              ),
            ),
          ],
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _currentPlaylist == null && _showAll
                    ? _buildPlaylistView()
                    : _buildSongList(),
          ),
        ],
      ),
      bottomSheet: _player.current != null ? _buildPlayer() : null,
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
                  subtitle: Text(
                    '${_allTracks.length} 首',
                    style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.play_circle_outline, size: 22),
                        tooltip: '播放全部',
                        onPressed: _playAllTracks,
                      ),
                      const Icon(Icons.chevron_right),
                    ],
                  ),
                  onTap: _showAllTracks,
                ),
                const Divider(),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    children: [
                      Text(
                        '我的歌单',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.grey.shade600,
                        ),
                      ),
                      const Spacer(),
                      IconButton(
                        icon: const Icon(Icons.add, size: 20),
                        onPressed: _createPlaylist,
                      ),
                    ],
                  ),
                ),
              ],
            );
          }
          final pl = _playlists[i - 1];
          return ListTile(
            leading: const CircleAvatar(
              child: Icon(Icons.queue_music, size: 20),
            ),
            title: Text(pl['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text(
              '${pl['song_count'] ?? 0} 首',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.play_circle_outline, size: 22),
                  tooltip: '播放全部',
                  onPressed: () => _playPlaylist(pl),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, size: 18),
                  onPressed: () async {
                    await ApiService().deletePlaylist(pl['id']);
                    _load();
                  },
                ),
              ],
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
          content: TextField(
            controller: c,
            autofocus: true,
            decoration: const InputDecoration(hintText: '歌单名称'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(ctx, c.text),
              child: const Text('创建'),
            ),
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建失败: $e')),
      );
    }
  }

  Widget _buildSongList() {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        itemCount: _currentSongs.length + 1,
        itemBuilder: (_, i) {
          if (i == 0) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 12, 4),
              child: Row(
                children: [
                  Text(
                    '${_currentSongs.length} 首',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                  const Spacer(),
                  FilledButton.tonalIcon(
                    onPressed: _currentSongs.isEmpty
                        ? null
                        : () => _start(_currentSongs, 0),
                    style: FilledButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                    ),
                    icon: const Icon(Icons.play_arrow_rounded, size: 18),
                    label: const Text(
                      '播放全部',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
            );
          }
          final s = _currentSongs[i - 1];
          final current = _player.isCurrent(s);
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: current ? Colors.blue : Colors.grey.shade200,
              child: Icon(
                current ? Icons.play_arrow : Icons.music_note,
                color: current ? Colors.white : Colors.grey.shade700,
                size: 20,
              ),
            ),
            title: Text(s['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text(
              _fmtSize(s['size'] ?? 0),
              style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
            ),
            trailing: _currentPlaylist != null
                ? IconButton(
                    icon: const Icon(Icons.remove_circle_outline, size: 18),
                    onPressed: () async {
                      await ApiService().removeSongFromPlaylist(
                        _currentPlaylist!['id'],
                        s['item_id'],
                      );
                      _openPlaylist(_currentPlaylist!);
                    },
                  )
                : null,
            onTap: () => _start(_currentSongs, i - 1),
          );
        },
      ),
    );
  }

  Widget _buildPlayer() {
    final song = _player.current!;
    final duration = _player.duration;
    final position = _player.position;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            (song['name'] ?? '').toString(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Slider(
            value: duration.inMilliseconds > 0
                ? (position.inMilliseconds / duration.inMilliseconds)
                    .clamp(0.0, 1.0)
                : 0,
            onChanged: (value) => _player.seek(
              Duration(milliseconds: (value * duration.inMilliseconds).round()),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  _fmt(position),
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
                Text(
                  _fmt(duration),
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ],
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                tooltip: _player.modeLabel,
                onPressed: _cycleMode,
                icon: Icon(_modeIcon(_player.mode), color: Colors.blueGrey),
              ),
              IconButton(
                onPressed: _player.previous,
                icon: const Icon(Icons.skip_previous),
              ),
              IconButton(
                onPressed: _player.buffering ? null : _player.toggle,
                icon: _player.buffering
                    ? const SizedBox(
                        width: 32,
                        height: 32,
                        child: CircularProgressIndicator(strokeWidth: 3),
                      )
                    : Icon(
                        _player.playing
                            ? Icons.pause_circle_filled
                            : Icons.play_circle_filled,
                        size: 48,
                      ),
              ),
              IconButton(
                onPressed: _player.next,
                icon: const Icon(Icons.skip_next),
              ),
              const SizedBox(width: 40),
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
