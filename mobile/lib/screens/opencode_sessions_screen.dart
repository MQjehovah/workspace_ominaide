import 'dart:async';

import 'package:flutter/material.dart';

import '../models/opencode_models.dart';
import '../services/api_service.dart';
import '../services/vibecoding_service.dart';
import '../theme/app_theme.dart';
import 'opencode_session_screen.dart';

/// Lists the OpenCode 2 sessions that live on the user's desktop machines.
///
/// The desktop `vibecoding-proxy` plugin owns the OpenCode server; this screen
/// only talks to it over the shared host channel.
class OpenCodeSessionsScreen extends StatefulWidget {
  const OpenCodeSessionsScreen({super.key, this.machineId});

  final String? machineId;

  @override
  State<OpenCodeSessionsScreen> createState() => _OpenCodeSessionsScreenState();
}

class _OpenCodeSessionsScreenState extends State<OpenCodeSessionsScreen> {
  final VibecodingService _service = VibecodingService();
  StreamSubscription<Map<String, dynamic>>? _sub;
  Timer? _timeout;
  Timer? _reconnect;

  List<Map<String, dynamic>> _machines = [];
  String? _machineId;
  List<OpenCodeSession> _sessions = [];
  bool _loading = true;
  String? _error;
  String? _pending;
  String? _serverUrl;
  DateTime _loadedAt = DateTime.now();

  @override
  void initState() {
    super.initState();
    _sub = _service.stream.listen(_onMessage);
    _service.connected.addListener(_onConnectionChanged);
    _service.ensureConnected();
    _machineId = widget.machineId;
    _loadMachines();
    _scheduleLoad();
    _reconnect = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!mounted) return;
      if (_service.connected.value) {
        _reconnect?.cancel();
        _reconnect = null;
        return;
      }
      _service.ensureConnected();
    });
  }

  @override
  void dispose() {
    _timeout?.cancel();
    _reconnect?.cancel();
    _service.connected.removeListener(_onConnectionChanged);
    _sub?.cancel();
    super.dispose();
  }

  void _onConnectionChanged() {
    if (!mounted) return;
    if (_service.connected.value) _scheduleLoad();
  }

  Future<void> _loadMachines() async {
    final raw = await ApiService().listVibecodingMachines();
    if (!mounted) return;
    final machines = raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    setState(() {
      if (machines.isNotEmpty) _machines = machines;
      if (_machineId == null || _machineId!.isEmpty) {
        final online = _machines.where((m) => m['online'] == true).toList();
        _machineId = online.isNotEmpty
            ? (online.first['machine_id'] ?? '').toString()
            : (_machines.isNotEmpty
                ? (_machines.first['machine_id'] ?? '').toString()
                : null);
      }
    });
  }

  void _scheduleLoad() {
    Future<void>.delayed(const Duration(milliseconds: 250), () {
      if (mounted) _loadSessions();
    });
  }

  void _loadSessions() {
    if (!_service.connected.value) {
      setState(() {
        _loading = false;
        _error = '未连接到服务器，请检查网络后下拉重试';
      });
      return;
    }
    final requestId = _service.newRequestId();
    _timeout?.cancel();
    setState(() {
      _loading = true;
      _error = null;
      _pending = requestId;
    });
    _service.requestSessions(requestId: requestId, machineId: _machineId);
    _timeout = Timer(const Duration(seconds: 12), () {
      if (!mounted || _pending != requestId) return;
      setState(() {
        _pending = null;
        _loading = false;
        _error = _machineId == null || _machineId!.isEmpty
            ? '没有在线的桌面设备。请启动 OmniAide 桌面端并启用 VibeCoding Proxy 插件'
            : '桌面端没有响应。请确认 OmniAide 桌面端在线、VibeCoding Proxy 插件已升级到 1.3.0，且本机已启动 OpenCode 2';
      });
    });
  }

  void _onMessage(Map<String, dynamic> msg) {
    if (!mounted) return;
    if (msg['type'] == 'device.status') {
      final machines = ((msg['machines'] as List?) ?? [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      setState(() {
        _machines = machines;
        if (_machineId == null && machines.isNotEmpty) {
          _machineId = (machines.first['machine_id'] ?? '').toString();
        }
      });
      return;
    }
    if (msg['type'] == 'oc.response') {
      final requestId = (msg['request_id'] ?? '').toString();
      if (requestId.isEmpty || requestId != _pending) return;
      _timeout?.cancel();
      final ok = msg['ok'] == true;
      final data = msg['data'];
      setState(() {
        _pending = null;
        _loading = false;
        if (!ok) {
          _error = (msg['error'] ?? '读取会话失败').toString();
          return;
        }
        _error = null;
        _loadedAt = DateTime.now();
        if (data is Map) {
          final server = data['server'];
          if (server is Map) {
            _serverUrl = (server['url'] ?? '').toString();
          }
          final sessions = (data['sessions'] as List?) ?? [];
          _sessions = sessions
              .whereType<Map>()
              .map((item) =>
                  OpenCodeSession.fromJson(Map<String, dynamic>.from(item)))
              .where((session) => session.id.isNotEmpty)
              .toList();
        }
      });
      return;
    }
    if (msg['type'] == 'oc.event' &&
        (msg['event'] ?? '') == 'sessions.changed') {
      _loadSessions();
    }
  }

  String _machineName(Map<String, dynamic> machine) {
    final name = (machine['name'] ?? '').toString();
    return name.isEmpty ? (machine['machine_id'] ?? '桌面端').toString() : name;
  }

  Map<String, List<OpenCodeSession>> get _grouped {
    final groups = <String, List<OpenCodeSession>>{};
    for (final session in _sessions) {
      final key = session.directory.isEmpty ? '其他' : session.directory;
      groups.putIfAbsent(key, () => []).add(session);
    }
    return groups;
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        backgroundColor: palette.background,
        title: const Text('OpenCode 会话'),
        actions: [
          ValueListenableBuilder<bool>(
            valueListenable: _service.connected,
            builder: (context, online, _) => Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Chip(
                avatar: Icon(
                  online ? Icons.link : Icons.link_off,
                  size: 15,
                  color: online ? palette.success : palette.muted,
                ),
                label: Text(
                  online ? '已连接' : '离线',
                  style: const TextStyle(fontSize: 11),
                ),
                visualDensity: VisualDensity.compact,
                side: BorderSide(color: palette.line),
                backgroundColor: palette.card,
              ),
            ),
          ),
          IconButton(
            tooltip: '刷新',
            onPressed: _loadSessions,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await _loadMachines();
          _loadSessions();
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: [
            if (_machines.length > 1) ...[
              _machineSelector(palette),
              const SizedBox(height: 12),
            ],
            if (_loading) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: const LinearProgressIndicator(minHeight: 3),
              ),
              const SizedBox(height: 12),
            ],
            if (_error != null) _errorCard(palette),
            if (!_loading && _error == null && _sessions.isEmpty)
              _emptyCard(palette),
            ..._sessionGroups(palette),
            const SizedBox(height: 12),
            Center(
              child: Text(
                _lastLoadedLabel(),
                style: TextStyle(fontSize: 10.5, color: palette.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _lastLoadedLabel() {
    final server = _serverUrl == null || _serverUrl!.isEmpty
        ? ''
        : ' · ${_serverUrl!.replaceFirst('http://', '').replaceFirst('https://', '')}';
    final time = TimeOfDay.fromDateTime(_loadedAt).format(context);
    return '更新于 $time$server';
  }

  Widget _machineSelector(AppPalette palette) {
    return SizedBox(
      height: 36,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: _machines.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final machine = _machines[index];
          final id = (machine['machine_id'] ?? '').toString();
          final selected = id == _machineId;
          final online =
              machine['online'] == true || machine['connected'] == true;
          return ChoiceChip(
            selected: selected,
            onSelected: (_) {
              if (_machineId == id) return;
              setState(() {
                _machineId = id;
                _sessions = [];
              });
              _loadSessions();
            },
            avatar: Icon(
              Icons.computer_rounded,
              size: 15,
              color: online
                  ? (selected ? palette.primary : palette.success)
                  : palette.muted,
            ),
            label: Text(
              _machineName(machine),
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
            side: BorderSide(
              color: selected ? palette.primary : palette.line,
            ),
            backgroundColor: palette.card,
            visualDensity: VisualDensity.compact,
          );
        },
      ),
    );
  }

  Widget _errorCard(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: palette.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.accent.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.wifi_off_rounded, size: 18, color: palette.accent),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _error!,
              style: TextStyle(fontSize: 12.5, height: 1.6, color: palette.ink),
            ),
          ),
          TextButton(onPressed: _loadSessions, child: const Text('重试')),
        ],
      ),
    );
  }

  Widget _emptyCard(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 26),
      decoration: BoxDecoration(
        color: palette.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: palette.line),
      ),
      child: Column(
        children: [
          Icon(Icons.terminal_rounded, size: 26, color: palette.muted),
          const SizedBox(height: 10),
          Text(
            '桌面端还没有 OpenCode 会话',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: palette.ink,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '在电脑上用 OpenCode 开始一个会话，然后回到这里下拉刷新。',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, height: 1.6, color: palette.muted),
          ),
        ],
      ),
    );
  }

  List<Widget> _sessionGroups(AppPalette palette) {
    final widgets = <Widget>[];
    for (final entry in _grouped.entries) {
      widgets.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(2, 8, 2, 8),
          child: Row(
            children: [
              Icon(Icons.folder_outlined, size: 13, color: palette.muted),
              const SizedBox(width: 5),
              Expanded(
                child: Text(
                  _shortPath(entry.key),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w600,
                    color: palette.muted,
                  ),
                ),
              ),
              Text(
                '${entry.value.length}',
                style: TextStyle(fontSize: 10.5, color: palette.muted),
              ),
            ],
          ),
        ),
      );
      for (final session in entry.value) {
        widgets.add(_sessionTile(palette, session));
        widgets.add(const SizedBox(height: 8));
      }
    }
    return widgets;
  }

  String _shortPath(String path) {
    final parts = path.split('/').where((part) => part.isNotEmpty).toList();
    if (parts.length <= 2) return path;
    return '…/${parts[parts.length - 2]}/${parts.last}';
  }

  Widget _sessionTile(AppPalette palette, OpenCodeSession session) {
    final meta = [
      if (session.agent.isNotEmpty) session.agent,
      if (session.model.isNotEmpty) session.model,
    ].join(' · ');
    return Material(
      color: palette.card,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _openSession(session),
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: palette.line),
          ),
          child: Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: palette.primarySoft,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  Icons.terminal_rounded,
                  size: 18,
                  color: palette.primary,
                ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        if (session.busy) ...[
                          Container(
                            width: 6,
                            height: 6,
                            margin: const EdgeInsets.only(right: 5),
                            decoration: BoxDecoration(
                              color: palette.success,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ],
                        Expanded(
                          child: Text(
                            session.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w700,
                              color: palette.ink,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      [
                        if (meta.isNotEmpty) meta,
                        if (session.busy) '运行中' else _relative(session.updated),
                      ].join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 10.5, color: palette.muted),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 18, color: palette.muted),
            ],
          ),
        ),
      ),
    );
  }

  String _relative(int millis) {
    if (millis <= 0) return '';
    final diff = DateTime.now().difference(
      DateTime.fromMillisecondsSinceEpoch(millis),
    );
    if (diff.inMinutes < 1) return '刚刚';
    if (diff.inMinutes < 60) return '${diff.inMinutes} 分钟前';
    if (diff.inHours < 24) return '${diff.inHours} 小时前';
    if (diff.inDays < 30) return '${diff.inDays} 天前';
    return '${(diff.inDays / 30).floor()} 个月前';
  }

  void _openSession(OpenCodeSession session) {
    Navigator.of(context)
        .push(
      MaterialPageRoute(
        builder: (_) => OpenCodeSessionScreen(
          machineId: _machineId,
          session: session,
        ),
      ),
    )
        .then((_) {
      if (mounted) _loadSessions();
    });
  }
}
