import 'dart:async';

import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../services/music_cache.dart';
import '../services/now_playing_service.dart';
import '../models/file_item.dart';

enum _PlayMode { sequential, repeatAll, repeatOne, shuffle }

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
  List<Map<String, dynamic>> _queue = [];
  int? _playingIndex;
  _PlayMode _mode = _PlayMode.sequential;
  List<int> _shuffleOrder = [];
  int _shufflePos = -1;
  bool _playing = false;
  bool _buffering = false;
  bool _downloading = false;
  String _downloadStatus = '';
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  @override
  void initState() {
    super.initState();
    _load();
    _loadMode();
    NowPlayingService().init();
    NowPlayingService().onCommand = _onRemoteCommand;
    _player.onPositionChanged.listen((p) => setState(() => _position = p));
    _player.onDurationChanged.listen((d) {
      setState(() => _duration = d);
      _updateNowPlaying();
    });
    _player.onPlayerComplete.listen((_) => _handleComplete());
  }

  @override
  void dispose() {
    NowPlayingService().onCommand = null;
    NowPlayingService().clear();
    _player.dispose();
    super.dispose();
  }

  Future<void> _loadMode() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString('music.playMode');
      final mode = _PlayMode.values.firstWhere(
        (value) => value.name == saved,
        orElse: () => _PlayMode.sequential,
      );
      if (mounted) setState(() => _mode = mode);
    } catch (_) {
      // Preferences are optional.
    }
  }

  Future<void> _saveMode() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('music.playMode', _mode.name);
    } catch (_) {
      // Ignore.
    }
  }

  void _cycleMode() {
    setState(() {
      _mode = _PlayMode.values[(_mode.index + 1) % _PlayMode.values.length];
    });
    if (_mode == _PlayMode.shuffle) {
      _resetShuffle(start: _playingIndex);
    }
    _saveMode();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        duration: const Duration(milliseconds: 900),
        content: Text(_modeLabel(_mode)),
      ),
    );
  }

  String _modeLabel(_PlayMode mode) {
    switch (mode) {
      case _PlayMode.sequential:
        return '顺序播放';
      case _PlayMode.repeatAll:
        return '列表循环';
      case _PlayMode.repeatOne:
        return '单曲循环';
      case _PlayMode.shuffle:
        return '随机播放';
    }
  }

  IconData _modeIcon(_PlayMode mode) {
    switch (mode) {
      case _PlayMode.sequential:
        return Icons.playlist_play_rounded;
      case _PlayMode.repeatAll:
        return Icons.repeat_rounded;
      case _PlayMode.repeatOne:
        return Icons.repeat_one_rounded;
      case _PlayMode.shuffle:
        return Icons.shuffle_rounded;
    }
  }

  void _resetShuffle({int? start}) {
    if (_queue.isEmpty) {
      _shuffleOrder = [];
      _shufflePos = -1;
      return;
    }
    _shuffleOrder = List<int>.generate(_queue.length, (i) => i)..shuffle();
    if (start != null && start >= 0 && start < _queue.length) {
      _shuffleOrder.remove(start);
      _shuffleOrder.insert(0, start);
      _shufflePos = 0;
    } else {
      _shufflePos = -1;
    }
  }

  int _nextShuffleIndex() {
    if (_queue.isEmpty) return 0;
    if (_shuffleOrder.length != _queue.length) {
      _resetShuffle(start: _playingIndex);
    }
    _shufflePos++;
    if (_shufflePos >= _shuffleOrder.length) {
      _resetShuffle();
      _shufflePos = 0;
    }
    return _shuffleOrder[_shufflePos];
  }

  int _prevShuffleIndex() {
    if (_queue.isEmpty) return 0;
    if (_shuffleOrder.length != _queue.length) {
      _resetShuffle(start: _playingIndex);
    }
    _shufflePos = _shufflePos <= 0 ? _shuffleOrder.length - 1 : _shufflePos - 1;
    return _shuffleOrder[_shufflePos];
  }

  Future<void> _handleComplete() async {
    final index = _playingIndex;
    if (index == null) return;
    switch (_mode) {
      case _PlayMode.repeatOne:
        try {
          await _player.seek(Duration.zero);
          await _player.resume();
          if (!mounted) return;
          setState(() {
            _playing = true;
            _position = Duration.zero;
          });
          _updateNowPlaying();
        } catch (_) {
          await _playSong(index);
        }
        break;
      case _PlayMode.repeatAll:
        await _playSong(index + 1 >= _queue.length ? 0 : index + 1);
        break;
      case _PlayMode.shuffle:
        await _playSong(_nextShuffleIndex());
        break;
      case _PlayMode.sequential:
        if (index + 1 < _queue.length) {
          await _playSong(index + 1);
        } else if (mounted) {
          setState(() {
            _playing = false;
            _position = Duration.zero;
          });
          _updateNowPlaying();
        }
        break;
    }
  }

  Future<void> _next() async {
    if (_queue.isEmpty) return;
    if (_mode == _PlayMode.shuffle) {
      await _playSong(_nextShuffleIndex());
      return;
    }
    final index = _playingIndex ?? 0;
    if (index + 1 < _queue.length) {
      await _playSong(index + 1);
    } else if (_mode == _PlayMode.repeatAll) {
      await _playSong(0);
    }
  }

  Future<void> _previous() async {
    if (_queue.isEmpty) return;
    if (_mode == _PlayMode.shuffle) {
      await _playSong(_prevShuffleIndex());
      return;
    }
    final index = _playingIndex ?? 0;
    if (index > 0) {
      await _playSong(index - 1);
    } else if (_mode == _PlayMode.repeatAll) {
      await _playSong(_queue.length - 1);
    }
  }

  void _updateNowPlaying() {
    final index = _playingIndex;
    if (index == null || index >= _queue.length) return;
    final song = _queue[index];
    NowPlayingService().update(
      title: (song['name'] ?? '音乐').toString(),
      duration: _duration,
      position: _position,
      playing: _playing,
    );
  }

  Future<void> _onRemoteCommand(String command, double? position) async {
    switch (command) {
      case 'play':
        if (!_playing) {
          await _player.resume();
          if (!mounted) return;
          setState(() => _playing = true);
          _updateNowPlaying();
        }
        break;
      case 'pause':
        if (_playing) {
          await _player.pause();
          if (!mounted) return;
          setState(() => _playing = false);
          _updateNowPlaying();
        }
        break;
      case 'toggle':
        if (_playing) {
          await _player.pause();
          if (!mounted) return;
          setState(() => _playing = false);
        } else {
          await _player.resume();
          if (!mounted) return;
          setState(() => _playing = true);
        }
        _updateNowPlaying();
        break;
      case 'next':
        await _next();
        break;
      case 'previous':
        await _previous();
        break;
      case 'seek':
        if (position != null) {
          final target = Duration(milliseconds: (position * 1000).round());
          await _player.seek(target);
          if (mounted) setState(() => _position = target);
          _updateNowPlaying();
        }
        break;
    }
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = ApiService();
      _playlists = await api.listPlaylists();
      _allTracks = await api.listAudioFiles();
      if (_showAll) {
        _currentSongs = _allTracks
            .map((f) =>
                {'file_id': f.id, 'name': f.originalName, 'size': f.size})
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

  Future<void> _playPlaylist(Map<String, dynamic> playlist) async {
    try {
      final songs = await ApiService().listPlaylistSongs(playlist['id']);
      if (!mounted) return;
      setState(() {
        _currentPlaylist = playlist;
        _currentSongs = songs;
        _showAll = false;
      });
      await _startQueue(songs, 0);
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
    await _startQueue(songs, 0);
  }

  Future<void> _playDisplayed() async {
    if (_currentSongs.isEmpty) return;
    await _startQueue(_currentSongs, 0);
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
                    title: Text(t.originalName,
                        style: const TextStyle(fontSize: 13)),
                    value: selected.contains(i) || inPlaylist,
                    onChanged: inPlaylist
                        ? null
                        : (v) {
                            if (v == true)
                              setDlgState(() => selected.add(i));
                            else
                              setDlgState(() => selected.remove(i));
                          },
                  );
                },
              ),
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('取消')),
              TextButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('添加')),
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

  Future<void> _startQueue(
    List<Map<String, dynamic>> songs,
    int index,
  ) async {
    if (songs.isEmpty) return;
    final start = index.clamp(0, songs.length - 1);
    setState(() {
      _queue = List<Map<String, dynamic>>.from(songs);
    });
    _resetShuffle(start: _mode == _PlayMode.shuffle ? start : null);
    await _playSong(start);
  }

  bool _isCurrentSong(Map<String, dynamic> song) {
    final index = _playingIndex;
    if (index == null || index >= _queue.length) return false;
    final current = _queue[index]['file_id'];
    return current != null && current == song['file_id'];
  }

  Future<void> _playSong(int index) async {
    if (index < 0 || index >= _queue.length) return;
    await _player.stop();
    final song = _queue[index];
    setState(() {
      _playingIndex = index;
      _playing = false;
      _buffering = true;
      _position = Duration.zero;
      _duration = Duration.zero;
    });
    try {
      final fileId = (song['file_id'] as num).toInt();
      final name = (song['name'] ?? 'track.mp3').toString();
      final cached = await MusicCache().cachedTrack(fileId, name);
      if (cached != null) {
        await _player.play(DeviceFileSource(cached.path));
      } else {
        // Stream immediately (Range-aware endpoint) and fill the cache in the
        // background so the next play is instant and works offline.
        final uri = await ApiService().fileStreamUri(fileId);
        try {
          await _player.play(UrlSource(uri.toString()));
        } catch (_) {
          final file = await MusicCache().cacheTrack(fileId, name);
          await _player.play(DeviceFileSource(file.path));
        }
        if (!mounted) return;
        unawaited(() async {
          try {
            await MusicCache().cacheTrack(fileId, name);
          } catch (_) {}
        }());
      }
      if (!mounted) return;
      setState(() => _playing = true);
      _updateNowPlaying();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('播放失败: $e')));
    } finally {
      if (mounted) setState(() => _buffering = false);
    }
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title:
            Text(_currentPlaylist != null ? _currentPlaylist!['name'] : '音乐'),
        actions: [
          IconButton(
            icon: const Icon(Icons.download_outlined),
            onPressed: _downloading ? null : _downloadCurrent,
            tooltip: _currentPlaylist != null ? '缓存整个歌单' : '缓存全部歌曲',
          ),
          if (_currentPlaylist != null) ...[
            IconButton(
                icon: const Icon(Icons.library_music_outlined),
                onPressed: () => setState(() {
                      _currentPlaylist = null;
                      _showAll = true;
                      _currentSongs = _allTracks
                          .map((f) => {
                                'file_id': f.id,
                                'name': f.originalName,
                                'size': f.size
                              })
                          .toList();
                    }),
                tooltip: '全部歌曲'),
            IconButton(
                icon: const Icon(Icons.playlist_add),
                onPressed: () => _showAddSong(_allTracks)),
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
                  subtitle: Text('${_allTracks.length} 首',
                      style:
                          TextStyle(fontSize: 11, color: Colors.grey.shade500)),
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
                  onTap: () => setState(() {
                    _showAll = true;
                    _currentSongs = _allTracks
                        .map((f) => {
                              'file_id': f.id,
                              'name': f.originalName,
                              'size': f.size
                            })
                        .toList();
                  }),
                ),
                const Divider(),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    children: [
                      Text('我的歌单',
                          style: TextStyle(
                              fontSize: 13, color: Colors.grey.shade600)),
                      const Spacer(),
                      IconButton(
                          icon: const Icon(Icons.add, size: 20),
                          onPressed: _createPlaylist),
                    ],
                  ),
                ),
              ],
            );
          }
          final pl = _playlists[i - 1];
          return ListTile(
            leading:
                const CircleAvatar(child: Icon(Icons.queue_music, size: 20)),
            title: Text(pl['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text('${pl['song_count'] ?? 0} 首',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
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
              decoration: const InputDecoration(hintText: '歌单名称')),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            TextButton(
                onPressed: () => Navigator.pop(ctx, c.text),
                child: const Text('创建')),
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('创建失败: $e')));
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
                    onPressed: _currentSongs.isEmpty ? null : _playDisplayed,
                    style: FilledButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                    ),
                    icon: const Icon(Icons.play_arrow_rounded, size: 18),
                    label: const Text('播放全部', style: TextStyle(fontSize: 12)),
                  ),
                ],
              ),
            );
          }
          final s = _currentSongs[i - 1];
          final current = _isCurrentSong(s);
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: current ? Colors.blue : Colors.grey.shade200,
              child: Icon(current ? Icons.play_arrow : Icons.music_note,
                  color: current ? Colors.white : Colors.grey.shade700,
                  size: 20),
            ),
            title: Text(s['name'] ?? '', style: const TextStyle(fontSize: 14)),
            subtitle: Text(_fmtSize(s['size'] ?? 0),
                style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
            trailing: _currentPlaylist != null
                ? IconButton(
                    icon: const Icon(Icons.remove_circle_outline, size: 18),
                    onPressed: () async {
                      await ApiService().removeSongFromPlaylist(
                          _currentPlaylist!['id'], s['item_id']);
                      _openPlaylist(_currentPlaylist!);
                    })
                : null,
            onTap: () => _startQueue(_currentSongs, i - 1),
          );
        },
      ),
    );
  }

  Widget _buildPlayer() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceVariant,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            (_queue.length > _playingIndex!
                        ? _queue[_playingIndex!]['name']
                        : '')
                    ?.toString() ??
                '',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Slider(
            value: _duration.inMilliseconds > 0
                ? _position.inMilliseconds / _duration.inMilliseconds
                : 0,
            onChanged: (v) => _player.seek(
                Duration(milliseconds: (v * _duration.inMilliseconds).round())),
            onChangeEnd: (_) => _updateNowPlaying(),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_fmt(_position),
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
                Text(_fmt(_duration),
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                tooltip: _modeLabel(_mode),
                onPressed: _cycleMode,
                icon: Icon(_modeIcon(_mode), color: Colors.blueGrey),
              ),
              IconButton(
                onPressed: _queue.isEmpty ? null : _previous,
                icon: const Icon(Icons.skip_previous),
              ),
              IconButton(
                  onPressed: _buffering
                      ? null
                      : () {
                          if (_playing) {
                            _player.pause();
                            setState(() => _playing = false);
                          } else {
                            _player.resume();
                            setState(() => _playing = true);
                          }
                          _updateNowPlaying();
                        },
                  icon: _buffering
                      ? const SizedBox(
                          width: 32,
                          height: 32,
                          child: CircularProgressIndicator(strokeWidth: 3))
                      : Icon(
                          _playing
                              ? Icons.pause_circle_filled
                              : Icons.play_circle_filled,
                          size: 48)),
              IconButton(
                onPressed: _queue.isEmpty ? null : _next,
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
