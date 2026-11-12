import 'dart:async';

import 'package:flutter/material.dart';

import '../models/opencode_models.dart';
import '../services/opencode_run_monitor.dart';
import '../services/vibecoding_service.dart';
import '../theme/app_theme.dart';
import '../widgets/chat_bubble.dart';

/// Live view of one remote OpenCode session: history, streaming output and a
/// composer that continues the same session on the desktop machine.
class OpenCodeSessionScreen extends StatefulWidget {
  const OpenCodeSessionScreen({
    super.key,
    required this.session,
    this.machineId,
  });

  final OpenCodeSession session;
  final String? machineId;

  @override
  State<OpenCodeSessionScreen> createState() => _OpenCodeSessionScreenState();
}

class _OpenCodeSessionScreenState extends State<OpenCodeSessionScreen> {
  final VibecodingService _service = VibecodingService();
  final OpenCodeRunMonitor _monitor = OpenCodeRunMonitor();
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();

  StreamSubscription<Map<String, dynamic>>? _sub;
  final List<OpenCodeMessage> _messages = [];
  String _draftText = '';
  String _draftReasoning = '';
  final List<OpenCodePart> _draftTools = [];
  String _draftMessageId = '';

  bool _loading = true;
  bool _running = false;
  String? _error;
  String? _cursor;

  String? _pendingHistory;
  String? _pendingOlder;
  String? _pendingPrompt;
  String? _pendingInterrupt;
  Timer? _historyTimer;

  @override
  void initState() {
    super.initState();
    _running = widget.session.busy;
    _sub = _service.stream.listen(_onMessage);
    _service.connected.addListener(_onConnectionChanged);
    _monitor.runs.addListener(_onRunStateChanged);
    _monitor.trackSession(
      widget.session,
      widget.machineId,
      running: widget.session.busy,
    );
    _service.ensureConnected();
    _loadHistory();
  }

  @override
  void dispose() {
    _historyTimer?.cancel();
    _monitor.runs.removeListener(_onRunStateChanged);
    _service.connected.removeListener(_onConnectionChanged);
    _sub?.cancel();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onRunStateChanged() {
    if (!mounted || !_running) return;
    if (!_monitor.wasTracked(widget.machineId, widget.session.id)) return;
    if (_monitor.isRunning(widget.machineId, widget.session.id)) return;
    setState(() => _running = false);
    _scheduleHistoryRefresh();
  }

  bool get _atBottom {
    if (!_scroll.hasClients) return true;
    return _scroll.position.pixels >= _scroll.position.maxScrollExtent - 80;
  }

  void _onConnectionChanged() {
    if (!mounted) return;
    if (!_service.connected.value) return;
    if (_running &&
        _monitor.wasTracked(widget.machineId, widget.session.id) &&
        !_monitor.isRunning(widget.machineId, widget.session.id)) {
      setState(() => _running = false);
    }
    if (_messages.isEmpty) {
      _loadHistory();
    } else {
      // Reconnect may have missed a completion or final text delta.
      _scheduleHistoryRefresh();
    }
  }

  Future<void> _loadHistory({String? cursor}) async {
    final requestId = _service.newRequestId();
    if (!mounted) return;
    setState(() {
      if (cursor == null) _loading = _messages.isEmpty;
      _error = null;
      if (cursor == null) {
        _pendingHistory = requestId;
      } else {
        _pendingOlder = requestId;
      }
    });
    _service.requestHistory(
      requestId: requestId,
      sessionId: widget.session.id,
      machineId: widget.machineId,
      cursor: cursor,
    );
  }

  void _scheduleHistoryRefresh() {
    _historyTimer?.cancel();
    _historyTimer = Timer(const Duration(milliseconds: 450), () {
      if (!mounted) return;
      _flushDraft();
      _loadHistory();
    });
  }

  void _flushDraft() {
    if (_draftText.trim().isEmpty && _draftTools.isEmpty) {
      _draftText = '';
      _draftReasoning = '';
      _draftTools.clear();
      return;
    }
    final parts = <OpenCodePart>[
      ..._draftTools,
      if (_draftText.trim().isNotEmpty)
        OpenCodePart(type: 'text', text: _draftText),
      if (_draftReasoning.trim().isNotEmpty)
        OpenCodePart(type: 'reasoning', text: _draftReasoning),
    ];
    _messages.add(
      OpenCodeMessage(
        id: _draftMessageId.isEmpty
            ? 'live-${DateTime.now().microsecondsSinceEpoch}'
            : _draftMessageId,
        role: 'assistant',
        model: widget.session.model,
        time: DateTime.now().millisecondsSinceEpoch,
        parts: parts,
      ),
    );
    _draftText = '';
    _draftReasoning = '';
    _draftTools.clear();
    _draftMessageId = '';
  }

  void _onMessage(Map<String, dynamic> msg) {
    if (!mounted) return;
    final type = (msg['type'] ?? '').toString();
    if (type == 'oc.response') {
      _handleResponse(msg);
      return;
    }
    if (type != 'oc.event') return;
    if ((msg['session_id'] ?? '').toString() != widget.session.id) return;
    final event = (msg['event'] ?? '').toString();
    final data = msg['data'] is Map
        ? Map<String, dynamic>.from(msg['data'] as Map)
        : const <String, dynamic>{};
    switch (event) {
      case 'session.text.started':
        _draftMessageId = (data['message_id'] ?? '').toString();
        _running = true;
        break;
      case 'session.text.delta':
        if (_draftMessageId.isEmpty) {
          _draftMessageId = (data['message_id'] ?? '').toString();
        }
        _draftText += (data['delta'] ?? '').toString();
        break;
      case 'session.text.ended':
        final text = (data['text'] ?? '').toString();
        if (text.isNotEmpty) _draftText = text;
        break;
      case 'session.reasoning.delta':
        _draftReasoning += (data['delta'] ?? '').toString();
        break;
      case 'session.tool.called':
        final input = data['input'];
        _draftTools.add(
          OpenCodePart(
            type: 'tool',
            name: '工具调用',
            status: 'running',
            input: input is Map
                ? Map<String, dynamic>.from(input)
                : const <String, dynamic>{},
          ),
        );
        break;
      case 'session.execution.started':
        _running = true;
        break;
      case 'session.execution.succeeded':
      case 'session.execution.failed':
      case 'session.execution.interrupted':
        _running = false;
        _scheduleHistoryRefresh();
        break;
      default:
        break;
    }
    if (event.startsWith('session.')) {
      setState(() {});
      _scrollToBottom();
    }
  }

  void _handleResponse(Map<String, dynamic> msg) {
    final requestId = (msg['request_id'] ?? '').toString();
    final ok = msg['ok'] == true;
    final data = msg['data'];
    if (requestId.isNotEmpty && requestId == _pendingPrompt) {
      _pendingPrompt = null;
      if (!ok) {
        final error = (msg['error'] ?? '发送失败').toString();
        _monitor.markStopped(widget.machineId, widget.session.id);
        if (mounted) {
          setState(() => _running = false);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(error)),
          );
        }
      }
      return;
    }
    if (requestId.isNotEmpty && requestId == _pendingInterrupt) {
      _pendingInterrupt = null;
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text((msg['error'] ?? '停止失败').toString())),
        );
      }
      return;
    }
    final isLatest = requestId.isNotEmpty && requestId == _pendingHistory;
    final isOlder = requestId.isNotEmpty && requestId == _pendingOlder;
    if (!isLatest && !isOlder) return;
    if (!ok) {
      setState(() {
        _pendingHistory = null;
        _pendingOlder = null;
        _loading = false;
        _error = (msg['error'] ?? '读取会话失败').toString();
      });
      return;
    }
    final payload = data is Map
        ? Map<String, dynamic>.from(data)
        : const <String, dynamic>{};
    final raw = (payload['messages'] as List?) ?? const [];
    final loaded = raw
        .whereType<Map>()
        .map(
            (item) => OpenCodeMessage.fromJson(Map<String, dynamic>.from(item)))
        .where((message) => message.parts.isNotEmpty)
        .toList();
    setState(() {
      if (isLatest) {
        _pendingHistory = null;
        _messages
          ..clear()
          ..addAll(loaded);
        _loading = false;
        _error = null;
        _cursor = payload['cursor']?.toString();
        _draftText = '';
        _draftReasoning = '';
        _draftTools.clear();
      } else {
        _pendingOlder = null;
        _messages.insertAll(0, loaded);
      }
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    if (!_atBottom) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  void _send() {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    if (!_service.connected.value) {
      _service.ensureConnected();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('实时连接已断开，正在重连，请稍后重试')),
      );
      return;
    }
    final requestId = _service.newRequestId();
    setState(() {
      _messages.add(
        OpenCodeMessage(
          id: 'local-${DateTime.now().microsecondsSinceEpoch}',
          role: 'user',
          time: DateTime.now().millisecondsSinceEpoch,
          parts: [OpenCodePart(type: 'text', text: text)],
        ),
      );
      _draftText = '';
      _draftReasoning = '';
      _draftTools.clear();
      _draftMessageId = '';
      _running = true;
      _pendingPrompt = requestId;
    });
    _input.clear();
    _service.ensureConnected();
    _monitor.markPromptSent(widget.session, widget.machineId);
    _service.sendPrompt(
      requestId: requestId,
      sessionId: widget.session.id,
      text: text,
      machineId: widget.machineId,
    );
    _scrollToBottom();
  }

  void _stop() {
    if (!_running) return;
    final requestId = _service.newRequestId();
    setState(() {
      _pendingInterrupt = requestId;
      _running = false;
    });
    _monitor.markStopped(widget.machineId, widget.session.id);
    _service.interruptSession(
      requestId: requestId,
      sessionId: widget.session.id,
      machineId: widget.machineId,
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        backgroundColor: palette.background,
        titleSpacing: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.session.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
            Text(
              [
                if (widget.session.agent.isNotEmpty) widget.session.agent,
                if (widget.session.model.isNotEmpty) widget.session.model,
              ].join(' · '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 10.5, color: palette.muted),
            ),
          ],
        ),
        actions: [
          if (_running)
            IconButton(
              tooltip: '停止执行',
              onPressed: _stop,
              icon: Icon(Icons.stop_circle_outlined, color: palette.accent),
            ),
          IconButton(
            tooltip: '刷新',
            onPressed: () => _loadHistory(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Column(
        children: [
          ValueListenableBuilder<bool>(
            valueListenable: _service.connected,
            builder: (context, online, _) {
              if (online) return const SizedBox.shrink();
              return Container(
                width: double.infinity,
                color: palette.accent.withValues(alpha: 0.08),
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.cloud_off_rounded,
                      size: 15,
                      color: palette.accent,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _running
                            ? '实时连接已断开，正在重连。桌面端任务可能仍在运行，'
                                '完成后会自动同步并通知。'
                            : '实时连接已断开，正在重连…',
                        style: TextStyle(
                          fontSize: 11,
                          height: 1.45,
                          color: palette.ink,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
          Expanded(child: _buildMessages(palette)),
          _buildComposer(palette),
        ],
      ),
    );
  }

  Widget _buildMessages(AppPalette palette) {
    final widgets = <Widget>[];
    if (_loading) {
      widgets.add(const Padding(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      ));
    }
    if (_error != null) {
      widgets.add(
        Container(
          margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: palette.card,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: palette.accent.withValues(alpha: 0.4)),
          ),
          child: Row(
            children: [
              Icon(Icons.error_outline, size: 16, color: palette.accent),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _error!,
                  style: TextStyle(fontSize: 12, color: palette.ink),
                ),
              ),
              TextButton(
                onPressed: () => _loadHistory(),
                child: const Text('重试'),
              ),
            ],
          ),
        ),
      );
    }
    if (_cursor != null && _cursor!.isNotEmpty && _messages.isNotEmpty) {
      widgets.add(
        Center(
          child: TextButton(
            onPressed: () => _loadHistory(cursor: _cursor),
            child: Text(
              '加载更早的消息',
              style: TextStyle(fontSize: 11.5, color: palette.primary),
            ),
          ),
        ),
      );
    }
    if (!_loading && _messages.isEmpty && _draftText.isEmpty) {
      widgets.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 60, 28, 0),
          child: Column(
            children: [
              Icon(Icons.forum_outlined, size: 26, color: palette.muted),
              const SizedBox(height: 10),
              Text(
                '这个会话还没有消息',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '在下面直接输入，就会在电脑上的同一个 OpenCode 会话里继续执行。',
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 11.5, height: 1.6, color: palette.muted),
              ),
            ],
          ),
        ),
      );
    }
    for (final message in _messages) {
      widgets.add(_MessageView(message: message));
      widgets.add(const SizedBox(height: 10));
    }
    if (_draftText.isNotEmpty ||
        _draftReasoning.isNotEmpty ||
        _draftTools.isNotEmpty ||
        _running) {
      final draft = OpenCodeMessage(
        id: 'draft',
        role: 'assistant',
        model: widget.session.model,
        parts: [
          ..._draftTools,
          if (_draftText.isNotEmpty)
            OpenCodePart(type: 'text', text: _draftText),
          if (_draftReasoning.isNotEmpty)
            OpenCodePart(type: 'reasoning', text: _draftReasoning),
        ],
      );
      widgets.add(_MessageView(message: draft, streaming: _running));
      widgets.add(const SizedBox(height: 10));
    }
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      children: widgets,
    );
  }

  Widget _buildComposer(AppPalette palette) {
    return Container(
      decoration: BoxDecoration(
        color: palette.card,
        border: Border(top: BorderSide(color: palette.line)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_running)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 12,
                        height: 12,
                        child: CircularProgressIndicator(
                          strokeWidth: 1.8,
                          color: palette.primary,
                        ),
                      ),
                      const SizedBox(width: 8),
                      ValueListenableBuilder<bool>(
                        valueListenable: _service.connected,
                        builder: (context, online, _) => Text(
                          online
                              ? 'OpenCode 正在执行，输出会实时同步'
                              : 'OpenCode 正在执行，连接中断，恢复后自动同步',
                          style: TextStyle(fontSize: 11, color: palette.muted),
                        ),
                      ),
                    ],
                  ),
                ),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      minLines: 1,
                      maxLines: 5,
                      textInputAction: TextInputAction.newline,
                      style: TextStyle(fontSize: 14, color: palette.ink),
                      decoration: InputDecoration(
                        hintText: '继续这个会话…',
                        hintStyle:
                            TextStyle(fontSize: 13, color: palette.muted),
                        isDense: true,
                        filled: true,
                        fillColor: palette.background,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 12,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(color: palette.line),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(color: palette.line),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(color: palette.primary),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ValueListenableBuilder<TextEditingValue>(
                    valueListenable: _input,
                    builder: (context, value, _) {
                      final enabled = value.text.trim().isNotEmpty;
                      return SizedBox(
                        width: 44,
                        height: 44,
                        child: Material(
                          color: enabled ? palette.primary : palette.line,
                          borderRadius: BorderRadius.circular(14),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(14),
                            onTap: enabled ? _send : null,
                            child: Icon(
                              Icons.arrow_upward_rounded,
                              size: 20,
                              color: enabled ? Colors.white : palette.muted,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MessageView extends StatelessWidget {
  const _MessageView({required this.message, this.streaming = false});

  final OpenCodeMessage message;
  final bool streaming;

  @override
  Widget build(BuildContext context) {
    if (message.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: ChatBubble(role: 'user', text: message.text),
      );
    }
    final palette = AppPalette.of(context);
    final tools = message.tools;
    final reasoning = message.reasoning;
    final text = message.text;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (tools.isNotEmpty) _ToolStrip(tools: tools, palette: palette),
        if (reasoning.isNotEmpty) _ReasoningBlock(text: reasoning),
        if (text.isNotEmpty || streaming)
          Align(
            alignment: Alignment.centerLeft,
            child: ChatBubble(
              role: 'assistant',
              text: text,
              streaming: streaming,
            ),
          ),
      ],
    );
  }
}

class _ToolStrip extends StatelessWidget {
  const _ToolStrip({required this.tools, required this.palette});

  final List<OpenCodePart> tools;
  final AppPalette palette;

  @override
  Widget build(BuildContext context) {
    final visible = tools.length > 4 ? tools.sublist(tools.length - 4) : tools;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final tool in visible) _chip(tool),
          if (tools.length > visible.length)
            _chip(OpenCodePart(
                type: 'tool', name: '+${tools.length - visible.length}')),
        ],
      ),
    );
  }

  Widget _chip(OpenCodePart tool) {
    final detail = _detail(tool);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: palette.primarySoft,
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.build_circle_outlined, size: 12, color: palette.primary),
          const SizedBox(width: 4),
          Text(
            detail.isEmpty ? tool.name : detail,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w600,
              color: palette.primary,
            ),
          ),
        ],
      ),
    );
  }

  String _detail(OpenCodePart tool) {
    if (tool.input.isEmpty) return tool.name;
    for (final key in ['command', 'filePath', 'path', 'pattern', 'preview']) {
      final value = tool.input[key];
      if (value is String && value.trim().isNotEmpty) {
        final line = value.split('\n').first.trim();
        if (line.isEmpty) continue;
        return line.length > 36 ? '${line.substring(0, 36)}…' : line;
      }
    }
    return tool.name;
  }
}

class _ReasoningBlock extends StatefulWidget {
  const _ReasoningBlock({required this.text});

  final String text;

  @override
  State<_ReasoningBlock> createState() => _ReasoningBlockState();
}

class _ReasoningBlockState extends State<_ReasoningBlock> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: () => setState(() => _open = !_open),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _open
                        ? Icons.keyboard_arrow_down_rounded
                        : Icons.keyboard_arrow_right_rounded,
                    size: 15,
                    color: palette.muted,
                  ),
                  const SizedBox(width: 3),
                  Icon(Icons.psychology_outlined,
                      size: 13, color: palette.muted),
                  const SizedBox(width: 4),
                  Text(
                    '思考过程',
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: palette.muted,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_open)
            Container(
              width: double.infinity,
              margin: const EdgeInsets.only(top: 4),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: palette.card,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: palette.line),
              ),
              child: Text(
                widget.text,
                style: TextStyle(
                  fontSize: 11,
                  height: 1.6,
                  color: palette.muted,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
