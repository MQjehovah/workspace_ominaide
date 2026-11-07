import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat_session.dart';
import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../services/speech_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'bots_screen.dart';
import 'voice_chat_screen.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  final String? initialQuery;
  final String? sessionId;
  final String? title;
  final String? contextLabel;

  /// When true and no [sessionId] is given, open the most recent conversation
  /// instead of starting a blank chat. Used by the 对话 tab.
  final bool autoLoadLatest;

  const ChatScreen({
    super.key,
    this.initialQuery,
    this.sessionId,
    this.title,
    this.contextLabel,
    this.autoLoadLatest = false,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _Message {
  final String role;
  String text;
  bool error = false;
  final int? id;

  _Message(this.role, this.text, {this.id});
}

class _ChatScreenState extends State<ChatScreen> {
  final List<_Message> _messages = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _loading = false;
  bool _bootstrapping = false;
  bool _hasOlder = false;
  bool _loadingOlder = false;
  bool _atBottom = true;
  bool _showJump = false;
  int? _oldestId;
  bool _contextVisible = true;
  bool _stopRequested = false;
  bool _listening = false;
  String _voiceBase = '';
  StreamSubscription<String>? _streamSub;
  Completer<void>? _streamDone;
  final ValueNotifier<bool> _canSend = ValueNotifier(false);

  late String _sessionId =
      widget.sessionId ?? 'mobile-${DateTime.now().microsecondsSinceEpoch}';
  String? _title;
  int? _botId;
  String? _botName;

  @override
  void initState() {
    super.initState();
    _title = widget.title;
    _scroll.addListener(_onScroll);
    _input.addListener(_onInputChanged);
    _bootstrap();
    if (widget.initialQuery != null && widget.initialQuery!.isNotEmpty) {
      _input.text = widget.initialQuery!;
      WidgetsBinding.instance.addPostFrameCallback((_) => _send());
    }
  }

  void _onInputChanged() {
    _canSend.value = _input.text.trim().isNotEmpty;
  }

  Future<void> _toggleVoice() async {
    if (_loading) return;
    if (_listening) {
      await speechService.stop();
      if (mounted) setState(() => _listening = false);
      return;
    }
    final available = await speechService.initialize(
      onStatus: _onSpeechStatus,
      onError: _onSpeechError,
    );
    if (!mounted) return;
    if (!available) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('无法使用语音识别，请检查麦克风权限')),
      );
      return;
    }
    final locale = await speechService.preferredLocale();
    if (!mounted) return;
    _voiceBase = _input.text.trim();
    setState(() => _listening = true);
    try {
      await speechService.start(
        localeId: locale,
        onResult: (text, isFinal) {
          if (!mounted || _loading) return;
          final joined = [_voiceBase, text.trim()]
              .where((value) => value.isNotEmpty)
              .join(' ');
          _input.text = joined;
          _input.selection = TextSelection.fromPosition(
            TextPosition(offset: _input.text.length),
          );
          _canSend.value = joined.isNotEmpty;
          if (isFinal && mounted) setState(() => _listening = false);
        },
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _listening = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('语音识别启动失败')),
      );
    }
  }

  void _onSpeechStatus(String status) {
    if (!mounted || !_listening) return;
    if (status == 'done' || status == 'notListening') {
      setState(() => _listening = false);
    }
  }

  void _onSpeechError(String message) {
    if (!mounted) return;
    setState(() => _listening = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('语音识别失败：$message')),
    );
  }

  void _onScroll() {
    if (!_scroll.hasClients) return;
    final atBottom =
        _scroll.position.maxScrollExtent - _scroll.position.pixels < 80;
    final showJump = !atBottom;
    if (atBottom == _atBottom && showJump == _showJump) return;
    setState(() {
      _atBottom = atBottom;
      _showJump = showJump;
    });
  }

  Future<void> _loadBot() async {
    await BotSelectionService().load();
    _botId = BotSelectionService().botId;
    _botName = BotSelectionService().botName;
    if (_botId != null) {
      if (mounted) setState(() {});
      return;
    }
    try {
      final bots = await ApiService().listBots();
      if (bots.isEmpty) return;
      final bot = bots.firstWhere(
        (b) => b['is_default'] == true,
        orElse: () => bots.first,
      );
      final id = (bot['id'] as num?)?.toInt();
      if (id == null) return;
      final name = (bot['name'] ?? 'AI 助理').toString();
      await BotSelectionService().select(id, name);
      _botId = id;
      _botName = name;
    } catch (_) {}
    if (mounted) setState(() {});
  }

  Future<void> _showBotPicker() async {
    List<Map<String, dynamic>> bots;
    try {
      bots = await ApiService().listBots();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(
                '加载角色失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
      return;
    }
    if (!mounted) return;
    final palette = AppPalette.of(context);
    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            Row(
              children: [
                Text(
                  '切换 AI 角色',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
                const Spacer(),
                TextButton(
                  onPressed: () async {
                    final before = _botId;
                    Navigator.pop(ctx);
                    await Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const BotsScreen()),
                    );
                    await _loadBot();
                    if (!mounted) return;
                    if (_botId != before) _newChat();
                    setState(() {});
                  },
                  child: const Text('管理'),
                ),
              ],
            ),
            for (final bot in bots)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: CircleAvatar(
                  radius: 17,
                  backgroundColor: palette.primarySoft,
                  child: Icon(Icons.smart_toy_outlined,
                      size: 18, color: palette.primary),
                ),
                title: Text((bot['name'] ?? 'AI 助理').toString()),
                subtitle: (bot['role'] ?? '').toString().isEmpty
                    ? null
                    : Text((bot['role'] ?? '').toString()),
                trailing: (bot['id'] as num?)?.toInt() == _botId
                    ? Icon(Icons.check_circle, size: 18, color: palette.primary)
                    : null,
                onTap: () => Navigator.pop(ctx, bot),
              ),
          ],
        ),
      ),
    );
    if (picked == null || !mounted) return;
    final id = (picked['id'] as num?)?.toInt();
    if (id == null) return;
    final name = (picked['name'] ?? 'AI 助理').toString();
    await BotSelectionService().select(id, name);
    if (!mounted) return;
    setState(() {
      _botId = id;
      _botName = name;
    });
    _newChat();
    if (mounted) setState(() {});
  }

  Future<void> _bootstrap() async {
    await _loadBot();
    if (widget.sessionId != null) {
      await _loadHistory();
      return;
    }
    if (!widget.autoLoadLatest || widget.initialQuery != null) return;
    _bootstrapping = true;
    try {
      final sessions = await ApiService().listChatSessions(botId: _botId);
      if (!mounted) return;
      if (sessions.isNotEmpty) {
        _sessionId = sessions.first.id;
        _title = sessions.first.title;
        await _loadHistory();
      }
    } catch (_) {
      // Offline: stay on a blank new conversation.
    } finally {
      if (mounted) setState(() => _bootstrapping = false);
    }
  }

  void _newChat() {
    setState(() {
      _sessionId = 'mobile-${DateTime.now().microsecondsSinceEpoch}';
      _title = null;
      _messages.clear();
      _loading = false;
      _bootstrapping = false;
      _hasOlder = false;
      _oldestId = null;
    });
    _input.clear();
  }

  void _openVoiceChat() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const VoiceChatScreen()),
    );
  }

  Future<void> _switchSession(ChatSession session) async {
    setState(() {
      _sessionId = session.id;
      _title = session.title;
      _messages.clear();
      _loading = false;
      _hasOlder = false;
      _oldestId = null;
    });
    await _loadHistory();
  }

  List<_Message> _messagesFromRows(List<Map<String, dynamic>> rows) {
    final loaded = <_Message>[];
    for (final row in rows) {
      final role = (row['role'] ?? 'assistant').toString();
      final content = (row['content'] ?? '').toString();
      if (content.isEmpty) continue;
      loaded.add(_Message(
        role == 'user' ? 'user' : 'assistant',
        content,
        id: row['id'] is int ? row['id'] as int : null,
      ));
    }
    return loaded;
  }

  Future<void> _loadHistory() async {
    try {
      final rows = await ApiService().loadChatHistory(
        sessionId: _sessionId,
        limit: 50,
      );
      if (!mounted || rows.isEmpty) return;
      // Never overwrite a turn that started before history arrived.
      if (_messages.isNotEmpty || _loading) return;
      final loaded = _messagesFromRows(rows);
      if (loaded.isEmpty) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(loaded);
        _oldestId = loaded.first.id;
        _hasOlder = rows.length >= 50;
      });
      _scrollToBottom(force: true, animate: false);
    } catch (_) {
      // Offline or first run: keep the local empty state.
    }
  }

  Future<void> _loadOlder() async {
    if (_loadingOlder || !_hasOlder || _oldestId == null) return;
    setState(() => _loadingOlder = true);
    try {
      final rows = await ApiService().loadChatHistory(
        sessionId: _sessionId,
        limit: 50,
        beforeId: _oldestId,
      );
      if (!mounted) return;
      final loaded = _messagesFromRows(rows);
      setState(() {
        if (loaded.isNotEmpty) {
          _messages.insertAll(0, loaded);
          _oldestId = loaded.first.id;
        }
        _hasOlder = rows.length >= 50;
        _loadingOlder = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingOlder = false);
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _loading) return;
    if (_listening) {
      await speechService.stop();
      if (mounted) setState(() => _listening = false);
    }
    _input.clear();

    final history = _messages
        .where((m) => m.text.isNotEmpty && !m.error)
        .toList()
        .reversed
        .take(20)
        .toList()
        .reversed
        .map((m) => {'role': m.role, 'content': m.text})
        .toList();

    final assistant = _Message('assistant', '');
    if (_title == null) {
      _title = text.length > 20 ? '${text.substring(0, 20)}…' : text;
    }
    setState(() {
      _messages.add(_Message('user', text));
      _messages.add(assistant);
      _loading = true;
    });
    _atBottom = true;
    _scrollToBottom(force: true);

    _stopRequested = false;
    final buffer = StringBuffer();
    var lastFlush = DateTime.now();
    final done = Completer<void>();
    _streamDone = done;
    final api = ApiService();
    if (_botId == null) await _loadBot();
    _streamSub = api
        .chatStream(
      text,
      history: history,
      sessionId: _sessionId,
      botId: _botId,
    )
        .listen(
      (chunk) {
        buffer.write(chunk);
        final now = DateTime.now();
        if (now.difference(lastFlush) >= const Duration(milliseconds: 50)) {
          lastFlush = now;
          if (mounted) setState(() => assistant.text = buffer.toString());
          _scrollToBottom();
        }
      },
      onError: (Object error, StackTrace stack) {
        if (!done.isCompleted) done.completeError(error);
      },
      onDone: () {
        if (!done.isCompleted) done.complete();
      },
      cancelOnError: true,
    );

    try {
      await done.future;
      if (mounted) {
        setState(() {
          if (buffer.isNotEmpty) assistant.text = buffer.toString();
          if (assistant.text.isEmpty) {
            assistant.text = _stopRequested ? '已停止生成' : '（无回复）';
          }
        });
      }
    } catch (e) {
      if (!mounted) return;
      final message = e.toString().replaceFirst('Exception: ', '');
      setState(() {
        assistant.error = true;
        assistant.text =
            buffer.isEmpty ? message : '${buffer.toString()}\n\n⚠️ $message';
      });
    } finally {
      if (mounted) setState(() => _loading = false);
      _streamSub = null;
      _streamDone = null;
    }
  }

  void _stop() {
    _stopRequested = true;
    _streamSub?.cancel();
    _streamSub = null;
    final done = _streamDone;
    if (done != null && !done.isCompleted) done.complete();
  }

  Future<void> _resendLastUser() async {
    if (_loading || _messages.isEmpty) return;
    String? lastUser;
    for (final message in _messages.reversed) {
      if (message.role == 'user') {
        lastUser = message.text;
        break;
      }
    }
    if (lastUser == null) return;
    setState(() {
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        _messages.removeLast();
      }
      if (_messages.isNotEmpty && _messages.last.role == 'user') {
        _messages.removeLast();
      }
    });
    _input.text = lastUser;
    await _send();
  }

  Future<void> _retry() => _resendLastUser();

  void _copyMessage(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('已复制')),
    );
  }

  Future<void> _showMessageActions(_Message message, int index) async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (sheetContext) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                dense: true,
                title: Text(
                  message.role == 'user' ? '你的消息' : 'AI 回复',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: palette.muted,
                  ),
                ),
              ),
              if (message.text.isNotEmpty)
                ListTile(
                  leading: const Icon(Icons.copy_rounded, size: 19),
                  title: const Text('复制'),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _copyMessage(message.text);
                  },
                ),
              if (message.role == 'user')
                ListTile(
                  leading: const Icon(Icons.edit_outlined, size: 19),
                  title: const Text('编辑并重发'),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _editUserMessage(index);
                  },
                ),
              if (message.role == 'assistant' &&
                  index == _messages.length - 1 &&
                  !_loading)
                ListTile(
                  leading: const Icon(Icons.refresh_rounded, size: 19),
                  title: const Text('重新生成'),
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _regenerateAt(index);
                  },
                ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _editUserMessage(int index) async {
    if (_loading || index < 0 || index >= _messages.length) return;
    final controller = TextEditingController(text: _messages[index].text);
    final text = await showDialog<String>(
      context: context,
      builder: (context) {
        final palette = AppPalette.of(context);
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '编辑并重发',
            style: TextStyle(fontSize: 16, color: palette.ink),
          ),
          content: TextField(
            controller: controller,
            autofocus: true,
            minLines: 3,
            maxLines: 8,
            decoration: const InputDecoration(hintText: '修改这条消息'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, controller.text.trim()),
              child: const Text('重发'),
            ),
          ],
        );
      },
    );
    controller.dispose();
    if (text == null || text.isEmpty) return;
    setState(() {
      _messages.removeRange(index, _messages.length);
    });
    _input.text = text;
    await _send();
  }

  Future<void> _regenerateAt(int assistantIndex) async {
    if (_loading) return;
    var userIndex = -1;
    for (var i = assistantIndex - 1; i >= 0; i--) {
      if (_messages[i].role == 'user') {
        userIndex = i;
        break;
      }
    }
    if (userIndex < 0) return;
    final text = _messages[userIndex].text;
    setState(() {
      _messages.removeRange(userIndex, _messages.length);
    });
    _input.text = text;
    await _send();
  }

  Future<void> _renameSession(ChatSession session) async {
    final controller = TextEditingController(text: session.title);
    final title = await showDialog<String>(
      context: context,
      builder: (context) {
        final palette = AppPalette.of(context);
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '重命名会话',
            style: TextStyle(fontSize: 16, color: palette.ink),
          ),
          content: TextField(
            controller: controller,
            autofocus: true,
            decoration: const InputDecoration(hintText: '会话名称'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, controller.text.trim()),
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
    controller.dispose();
    if (title == null || title.isEmpty) return;
    final ok = await ApiService().renameChatSession(session.id, title);
    if (!mounted) return;
    if (ok) {
      if (session.id == _sessionId) setState(() => _title = title);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('会话已重命名')),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('重命名失败')),
      );
    }
  }

  Future<void> _deleteSession(ChatSession session) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除会话？'),
        content: Text('「${session.title}」及其消息会被删除。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ok = await ApiService().deleteChatSession(session.id);
    if (!mounted) return;
    if (ok) {
      if (session.id == _sessionId) _newChat();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('会话已删除')),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('删除失败')),
      );
    }
  }

  void _scrollToBottom({bool force = false, bool animate = true}) {
    if (!force && !_atBottom) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final target = _scroll.position.maxScrollExtent;
      if (!animate) {
        _scroll.jumpTo(target);
        return;
      }
      _scroll.animateTo(
        target,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  void _applyPrompt(String text) {
    _input.text = text;
    _input.selection = TextSelection.fromPosition(
      TextPosition(offset: _input.text.length),
    );
    _send();
  }

  Future<void> _showReferences() async {
    final api = ApiService();
    final now = DateTime.now();
    final start = DateTime(now.year, now.month, now.day);
    List<Map<String, dynamic>> events = [];
    List<Map<String, dynamic>> todos = [];
    try {
      events = await api.listScheduleEvents(
        start: start.toIso8601String(),
        end: start.add(const Duration(days: 1)).toIso8601String(),
      );
    } catch (_) {}
    try {
      todos = await api.listTodoItems();
    } catch (_) {}
    if (!mounted) return;

    final picked = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (context) {
        final palette = AppPalette.of(context);
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              Text(
                '引用到今天的内容',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 8),
              if (events.isEmpty && todos.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  child: Text(
                    '今天没有日程或待办可以引用。',
                    style: TextStyle(fontSize: 13, color: palette.muted),
                  ),
                ),
              for (final event in events.take(6))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.event_outlined, color: palette.primary),
                  title: Text(
                    (event['title'] ?? '日程').toString(),
                    style: TextStyle(fontSize: 13, color: palette.ink),
                  ),
                  subtitle: Text(
                    (event['start_time'] ?? '')
                        .toString()
                        .replaceFirst('T', ' '),
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                  onTap: () => Navigator.pop(
                    context,
                    '关于今天的日程「${event['title']}」，',
                  ),
                ),
              for (final todo in todos.take(6))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading:
                      Icon(Icons.check_circle_outline, color: palette.success),
                  title: Text(
                    (todo['title'] ?? '待办').toString(),
                    style: TextStyle(fontSize: 13, color: palette.ink),
                  ),
                  subtitle: Text(
                    '待办',
                    style: TextStyle(fontSize: 11, color: palette.muted),
                  ),
                  onTap: () => Navigator.pop(
                    context,
                    '关于待办「${todo['title']}」，',
                  ),
                ),
            ],
          ),
        );
      },
    );
    if (picked == null || !mounted) return;
    _input.text = picked + _input.text;
    _input.selection = TextSelection.fromPosition(
      TextPosition(offset: _input.text.length),
    );
  }

  Future<void> _showHistory() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppPalette.of(context).card,
      builder: (sheetContext) {
        final palette = AppPalette.of(sheetContext);
        return SafeArea(
          child: FutureBuilder<List<ChatSession>>(
            future: ApiService().listChatSessions(botId: _botId),
            builder: (context, snapshot) {
              final items = snapshot.data ?? [];
              return ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                children: [
                  Text(
                    '会话',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: palette.ink,
                    ),
                  ),
                  const SizedBox(height: 8),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading:
                        Icon(Icons.add_circle_outline, color: palette.primary),
                    title: Text(
                      '新对话',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: palette.primary,
                      ),
                    ),
                    onTap: () {
                      Navigator.pop(sheetContext);
                      _newChat();
                    },
                  ),
                  if (snapshot.connectionState == ConnectionState.waiting)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (items.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 20),
                      child: Text(
                        '还没有历史会话。',
                        style: TextStyle(fontSize: 13, color: palette.muted),
                      ),
                    ),
                  for (final session in items.take(30))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        session.id == _sessionId
                            ? Icons.chat_bubble_rounded
                            : Icons.chat_bubble_outline,
                        color: session.id == _sessionId
                            ? palette.primary
                            : palette.muted,
                      ),
                      title: Text(
                        session.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: session.id == _sessionId
                              ? FontWeight.w800
                              : FontWeight.w500,
                          color: palette.ink,
                        ),
                      ),
                      subtitle: Text(
                        relativeTimeLabel(session.updatedAt),
                        style: TextStyle(fontSize: 11, color: palette.muted),
                      ),
                      trailing: PopupMenuButton<String>(
                        icon: Icon(
                          Icons.more_horiz_rounded,
                          size: 18,
                          color: palette.muted,
                        ),
                        onSelected: (value) {
                          Navigator.pop(sheetContext);
                          if (value == 'rename') {
                            _renameSession(session);
                          } else if (value == 'delete') {
                            _deleteSession(session);
                          }
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: 'rename', child: Text('重命名')),
                          PopupMenuItem(
                            value: 'delete',
                            child:
                                Text('删除', style: TextStyle(color: Colors.red)),
                          ),
                        ],
                      ),
                      onTap: () {
                        Navigator.pop(sheetContext);
                        _switchSession(session);
                      },
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    speechService.cancel();
    _streamSub?.cancel();
    final done = _streamDone;
    if (done != null && !done.isCompleted) done.complete();
    _scroll.removeListener(_onScroll);
    _input.removeListener(_onInputChanged);
    _canSend.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              palette.primarySoft.withValues(alpha: 0.55),
              palette.background,
              palette.background,
            ],
            stops: const [0, 0.32, 1],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _buildTopBar(palette),
              if (widget.contextLabel != null && _contextVisible)
                _buildContextBanner(palette),
              Expanded(
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: _bootstrapping
                          ? Center(
                              child: CircularProgressIndicator(
                                  color: palette.primary),
                            )
                          : _messages.isEmpty
                              ? _buildEmpty(palette)
                              : ListView.builder(
                                  controller: _scroll,
                                  padding:
                                      const EdgeInsets.fromLTRB(14, 10, 14, 14),
                                  itemCount:
                                      _messages.length + (_hasOlder ? 1 : 0),
                                  itemBuilder: (context, index) {
                                    if (_hasOlder && index == 0) {
                                      return Padding(
                                        padding:
                                            const EdgeInsets.only(bottom: 6),
                                        child: Center(
                                          child: TextButton.icon(
                                            onPressed: _loadingOlder
                                                ? null
                                                : _loadOlder,
                                            icon: _loadingOlder
                                                ? const SizedBox(
                                                    width: 14,
                                                    height: 14,
                                                    child:
                                                        CircularProgressIndicator(
                                                      strokeWidth: 2,
                                                    ),
                                                  )
                                                : const Icon(
                                                    Icons.history_rounded,
                                                    size: 15,
                                                  ),
                                            label: Text(
                                              _loadingOlder ? '加载中…' : '加载更早消息',
                                              style:
                                                  const TextStyle(fontSize: 11),
                                            ),
                                          ),
                                        ),
                                      );
                                    }
                                    final messageIndex =
                                        index - (_hasOlder ? 1 : 0);
                                    final message = _messages[messageIndex];
                                    final isLast =
                                        messageIndex == _messages.length - 1;
                                    return Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        GestureDetector(
                                          onLongPress: () =>
                                              _showMessageActions(
                                            message,
                                            messageIndex,
                                          ),
                                          child: ChatBubble(
                                            role: message.role,
                                            text: message.text,
                                            streaming: isLast && _loading,
                                            error: message.error,
                                            onRetry:
                                                message.error ? _retry : null,
                                          ),
                                        ),
                                        if (isLast &&
                                            !_loading &&
                                            message.role == 'assistant' &&
                                            !message.error)
                                          Padding(
                                            padding: const EdgeInsets.only(
                                              left: 38,
                                              top: 1,
                                              bottom: 3,
                                            ),
                                            child: Row(
                                              mainAxisSize: MainAxisSize.min,
                                              children: [
                                                TextButton.icon(
                                                  onPressed: () => _copyMessage(
                                                      message.text),
                                                  icon: const Icon(
                                                    Icons.copy_rounded,
                                                    size: 14,
                                                  ),
                                                  label: const Text('复制'),
                                                  style: TextButton.styleFrom(
                                                    foregroundColor:
                                                        palette.muted,
                                                    textStyle: const TextStyle(
                                                      fontSize: 10,
                                                    ),
                                                    minimumSize: Size.zero,
                                                    padding: const EdgeInsets
                                                        .symmetric(
                                                      horizontal: 6,
                                                      vertical: 2,
                                                    ),
                                                  ),
                                                ),
                                                TextButton.icon(
                                                  onPressed: _resendLastUser,
                                                  icon: const Icon(
                                                    Icons.refresh_rounded,
                                                    size: 14,
                                                  ),
                                                  label: const Text('重新生成'),
                                                  style: TextButton.styleFrom(
                                                    foregroundColor:
                                                        palette.muted,
                                                    textStyle: const TextStyle(
                                                      fontSize: 10,
                                                    ),
                                                    minimumSize: Size.zero,
                                                    padding: const EdgeInsets
                                                        .symmetric(
                                                      horizontal: 6,
                                                      vertical: 2,
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                      ],
                                    );
                                  },
                                ),
                    ),
                    if (_showJump)
                      Positioned(
                        right: 14,
                        bottom: 14,
                        child: FloatingActionButton.small(
                          heroTag: null,
                          backgroundColor: palette.card,
                          foregroundColor: palette.primary,
                          elevation: 2,
                          onPressed: () {
                            setState(() => _atBottom = true);
                            _scrollToBottom(force: true);
                          },
                          child: const Icon(Icons.arrow_downward_rounded,
                              size: 19),
                        ),
                      ),
                  ],
                ),
              ),
              _buildComposer(palette),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 4, 10, 8),
      decoration: BoxDecoration(
        color: Colors.transparent,
        border: Border(
          bottom: BorderSide(color: palette.line.withValues(alpha: 0.65)),
        ),
      ),
      child: Row(
        children: [
          if (Navigator.of(context).canPop()) ...[
            RoundIconButton(
              icon: Icons.chevron_left_rounded,
              onTap: () => Navigator.maybePop(context),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: InkWell(
              onTap: _showHistory,
              borderRadius: BorderRadius.circular(10),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _title ?? '新对话',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              color: palette.ink,
                            ),
                          ),
                          Text(
                            _loading
                                ? '正在生成…'
                                : (_botName == null
                                    ? '点击切换会话'
                                    : '$_botName · 点击切换会话'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style:
                                TextStyle(fontSize: 10.5, color: palette.muted),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      Icons.expand_more_rounded,
                      size: 17,
                      color: palette.muted,
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          RoundIconButton(
            icon: Icons.smart_toy_outlined,
            tooltip: '切换 AI 角色',
            onTap: _showBotPicker,
          ),
          const SizedBox(width: 6),
          RoundIconButton(
            icon: Icons.graphic_eq_rounded,
            tooltip: '语音对话',
            onTap: _openVoiceChat,
          ),
          const SizedBox(width: 6),
          RoundIconButton(
            icon: Icons.add_rounded,
            tooltip: '新对话',
            onTap: _newChat,
          ),
        ],
      ),
    );
  }

  Widget _buildContextBanner(AppPalette palette) {
    return Container(
      margin: const EdgeInsets.fromLTRB(14, 8, 14, 0),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: palette.primarySoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: palette.line),
      ),
      child: Row(
        children: [
          TagDot(color: palette.primary),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              widget.contextLabel!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
                color: palette.primary,
              ),
            ),
          ),
          InkWell(
            onTap: () => setState(() => _contextVisible = false),
            borderRadius: BorderRadius.circular(10),
            child: Padding(
              padding: const EdgeInsets.all(2),
              child: Icon(
                Icons.close_rounded,
                size: 14,
                color: palette.muted,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmpty(AppPalette palette) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 26, 22, 20),
      children: [
        Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [palette.primaryLight, palette.primary],
            ),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: palette.primary.withValues(alpha: 0.24),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: const Icon(Icons.auto_awesome, color: Colors.white, size: 28),
        ),
        const SizedBox(height: 16),
        Text(
          '今天想先处理什么？',
          style: TextStyle(
            fontSize: 21,
            height: 1.15,
            letterSpacing: -0.4,
            fontWeight: FontWeight.w800,
            color: palette.ink,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '可以直接问，也可以让我查日程、待办、文件，或帮你起草回复。',
          style: TextStyle(fontSize: 12.5, height: 1.65, color: palette.muted),
        ),
        const SizedBox(height: 20),
        Text(
          '快捷开始',
          style: TextStyle(
            fontSize: 10,
            letterSpacing: 1,
            fontWeight: FontWeight.w700,
            color: palette.muted,
          ),
        ),
        const SizedBox(height: 8),
        for (final prompt in const [
          '帮我看看今天最重要的三件事',
          '整理一下我的收件箱',
          '写本周周报',
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: AppCard(
              onTap: () => _applyPrompt(prompt),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              child: Row(
                children: [
                  Container(
                    width: 30,
                    height: 30,
                    decoration: BoxDecoration(
                      color: palette.primarySoft,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      Icons.bolt_rounded,
                      size: 16,
                      color: palette.primary,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      prompt,
                      style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                        color: palette.ink,
                      ),
                    ),
                  ),
                  Icon(
                    Icons.chevron_right_rounded,
                    size: 17,
                    color: palette.muted,
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildComposer(AppPalette palette) {
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 6, 10, 8),
      decoration: BoxDecoration(
        color: palette.background.withValues(alpha: 0.94),
        border: Border(
          top: BorderSide(color: palette.line.withValues(alpha: 0.8)),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_listening)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: palette.accent.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.graphic_eq_rounded,
                      size: 15,
                      color: palette.accent,
                    ),
                    const SizedBox(width: 5),
                    Expanded(
                      child: Text(
                        '正在听… 说完点麦克风停止',
                        style: TextStyle(
                          fontSize: 10.5,
                          color: palette.accent,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          Container(
            padding: const EdgeInsets.fromLTRB(6, 4, 6, 4),
            decoration: BoxDecoration(
              color: palette.card,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: palette.line),
              boxShadow: [
                BoxShadow(
                  color: palette.ink.withValues(alpha: 0.05),
                  blurRadius: 14,
                  offset: const Offset(0, 5),
                ),
              ],
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                InkWell(
                  onTap: _showReferences,
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: palette.primarySoft,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.add_rounded,
                      size: 20,
                      color: palette.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 5),
                Expanded(
                  child: TextField(
                    controller: _input,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    style: TextStyle(fontSize: 14, color: palette.ink),
                    cursorColor: palette.primary,
                    textAlignVertical: TextAlignVertical.center,
                    decoration: InputDecoration(
                      hintText: '继续问，或让我处理一件事…',
                      isDense: true,
                      filled: false,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 9,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                Tooltip(
                  message: _listening ? '停止语音输入' : '语音输入',
                  child: InkWell(
                    onTap: _loading ? null : _toggleVoice,
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color:
                            _listening ? palette.accent : palette.primarySoft,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        _listening
                            ? Icons.stop_rounded
                            : Icons.mic_none_rounded,
                        size: 19,
                        color: _listening ? Colors.white : palette.primary,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 5),
                ValueListenableBuilder<bool>(
                  valueListenable: _canSend,
                  builder: (context, canSend, _) {
                    final enabled = _loading || canSend;
                    return InkWell(
                      onTap: !enabled ? null : (_loading ? _stop : _send),
                      borderRadius: BorderRadius.circular(13),
                      child: Opacity(
                        opacity: enabled ? 1 : 0.45,
                        child: Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [palette.primaryLight, palette.primary],
                            ),
                            borderRadius: BorderRadius.circular(13),
                            boxShadow: [
                              BoxShadow(
                                color: palette.primary.withValues(alpha: 0.24),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: Icon(
                            _loading ? Icons.stop_rounded : Icons.send_rounded,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
