import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'api_service.dart';

/// Persistent cache for music tracks played from the server.
///
/// Files live in Application Support (not the temporary directory, which iOS
/// may purge), keyed by file id so renames or duplicate song names never
/// collide. A track is downloaded only on the first play; later plays use the
/// local copy. The cache is kept under [maxBytes] with a simple LRU eviction
/// based on last-access time.
class MusicCache {
  static final MusicCache _instance = MusicCache._();
  factory MusicCache() => _instance;
  MusicCache._();

  static const int maxBytes = 512 * 1024 * 1024; // 512 MB

  Directory? _directory;
  final Map<int, Future<File>> _inflight = {};

  Future<Directory> _cacheDirectory() async {
    final cached = _directory;
    if (cached != null) return cached;
    final support = await getApplicationSupportDirectory();
    final dir = Directory('${support.path}/music_cache');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    _directory = dir;
    return dir;
  }

  String _safeName(String name) {
    var base = name.trim().replaceAll(RegExp(r'[\\/:*?"<>|\n\r\t]'), '_');
    if (base.isEmpty) base = 'track';
    if (!base.contains('.')) base = '$base.mp3';
    if (base.length > 96) {
      final dot = base.lastIndexOf('.');
      final ext = dot >= 0 ? base.substring(dot) : '';
      base = base.substring(0, 96 - ext.length) + ext;
    }
    return base;
  }

  File _targetFile(Directory dir, int fileId, String name) =>
      File('${dir.path}/${fileId}_${_safeName(name)}');

  /// Return an already downloaded track, or null when it is not cached yet.
  Future<File?> cachedTrack(int fileId, String name) async {
    final dir = await _cacheDirectory();
    final target = _targetFile(dir, fileId, name);
    if (!await target.exists()) return null;
    final length = await target.length();
    if (length <= 0) {
      try {
        await target.delete();
      } catch (_) {}
      return null;
    }
    try {
      await target.setLastModified(DateTime.now());
    } catch (_) {}
    return target;
  }

  /// Return the cached track for [fileId], downloading it on first play.
  Future<File> cacheTrack(int fileId, String name) {
    return getOrDownload(fileId, name, download: (destination) async {
      final request = await ApiService().getFileDownloadRequest(fileId);
      await _downloadTo(request.uri, request.headers, destination);
    });
  }

  Future<void> _downloadTo(
    Uri uri,
    Map<String, String> headers,
    File destination,
  ) async {
    final client = http.Client();
    IOSink? sink;
    try {
      final request = http.Request('GET', uri);
      request.headers.addAll(headers);
      final response =
          await client.send(request).timeout(const Duration(seconds: 30));
      if (response.statusCode != 200) {
        throw Exception('Download failed: ${response.statusCode}');
      }
      sink = destination.openWrite();
      await for (final chunk
          in response.stream.timeout(const Duration(seconds: 120))) {
        sink.add(chunk);
      }
      await sink.flush();
    } finally {
      await sink?.close();
      client.close();
    }
  }

  /// Returns the cached track, downloading it with [download] if missing.
  /// Concurrent calls for the same track share one download.
  Future<File> getOrDownload(
    int fileId,
    String name, {
    required Future<void> Function(File destination) download,
  }) {
    final pending = _inflight[fileId];
    if (pending != null) return pending;

    final future = _load(fileId, name, download).whenComplete(() {
      _inflight.remove(fileId);
    });
    _inflight[fileId] = future;
    return future;
  }

  Future<File> _load(
    int fileId,
    String name,
    Future<void> Function(File destination) download,
  ) async {
    final dir = await _cacheDirectory();
    final target = _targetFile(dir, fileId, name);

    if (await target.exists()) {
      final length = await target.length();
      if (length > 0) {
        // Best-effort LRU: touching the file keeps recently played tracks.
        try {
          await target.setLastModified(DateTime.now());
        } catch (_) {}
        return target;
      }
      await target.delete();
    }

    final part = File('${target.path}.part');
    try {
      await download(part);
      final length = await part.length();
      if (length == 0) throw Exception('下载的音乐文件为空');
      if (await target.exists()) await target.delete();
      await part.rename(target.path);
      await _trim();
      return target;
    } catch (_) {
      if (await part.exists()) {
        try {
          await part.delete();
        } catch (_) {}
      }
      rethrow;
    }
  }

  /// Total bytes currently occupied by cached music.
  Future<int> size() async {
    final dir = await _cacheDirectory();
    var total = 0;
    await for (final entity in dir.list()) {
      if (entity is File && !entity.path.endsWith('.part')) {
        try {
          total += await entity.length();
        } catch (_) {}
      }
    }
    return total;
  }

  /// Remove every cached track.
  Future<void> clear() async {
    final dir = await _cacheDirectory();
    await for (final entity in dir.list()) {
      if (entity is File) {
        try {
          await entity.delete();
        } catch (_) {}
      }
    }
  }

  Future<void> _trim() async {
    final dir = await _cacheDirectory();
    final entries = <({File file, int size, DateTime modified})>[];
    var total = 0;
    await for (final entity in dir.list()) {
      if (entity is! File || entity.path.endsWith('.part')) continue;
      try {
        final stat = await entity.stat();
        total += stat.size;
        entries.add((file: entity, size: stat.size, modified: stat.modified));
      } catch (_) {}
    }
    if (total <= maxBytes) return;

    entries.sort((a, b) => a.modified.compareTo(b.modified));
    for (final entry in entries) {
      if (total <= maxBytes) break;
      try {
        await entry.file.delete();
        total -= entry.size;
      } catch (_) {}
    }
  }
}
