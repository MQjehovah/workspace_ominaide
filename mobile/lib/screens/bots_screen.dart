import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Manage AI roles/bots and choose the one used for chat.
class BotsScreen extends StatefulWidget {
  const BotsScreen({super.key});

  @override
  State<BotsScreen> createState() => _BotsScreenState();
}

class _BotsScreenState extends State<BotsScreen> {
  List<Map<String, dynamic>> _bots = [];
  bool _loading = true;
  String? _error;
  int? _selectedId;

  @override
  void initState() {
    super.initState();
    BotSelectionService().load().then((_) {
      if (mounted) setState(() => _selectedId = BotSelectionService().botId);
    });
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final bots = await ApiService().listBots();
      if (!mounted) return;
      setState(() {
        _bots = bots;
        _loading = false;
        _selectedId ??= _defaultBotId(bots);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  int? _defaultBotId(List<Map<String, dynamic>> bots) {
    if (bots.isEmpty) return null;
    final preferred = bots.firstWhere(
      (b) => b['is_default'] == true,
      orElse: () => bots.first,
    );
    return (preferred['id'] as num?)?.toInt();
  }

  Future<void> _select(Map<String, dynamic> bot) async {
    final id = (bot['id'] as num?)?.toInt();
    if (id == null) return;
    final name = (bot['name'] ?? 'AI 助理').toString();
    await BotSelectionService().select(id, name);
    if (!mounted) return;
    Navigator.pop(context, true);
  }

  Future<void> _edit([Map<String, dynamic>? bot]) async {
    final nameCtl = TextEditingController(text: (bot?['name'] ?? '').toString());
    final roleCtl = TextEditingController(text: (bot?['role'] ?? '').toString());
    final promptCtl =
        TextEditingController(text: (bot?['system_prompt'] ?? '').toString());
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(bot == null ? '新建 AI 角色' : '编辑 AI 角色'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameCtl,
                autofocus: true,
                decoration: const InputDecoration(labelText: '名称'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: roleCtl,
                decoration: const InputDecoration(
                  labelText: '角色（可选）',
                  hintText: '例如：写作助手 / 英语老师',
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: promptCtl,
                minLines: 4,
                maxLines: 8,
                decoration: const InputDecoration(
                  labelText: '系统提示词（可选）',
                  hintText: '描述这个角色的说话方式、职责和边界',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    final name = nameCtl.text.trim();
    final role = roleCtl.text.trim();
    final prompt = promptCtl.text.trim();
    nameCtl.dispose();
    roleCtl.dispose();
    promptCtl.dispose();
    if (!mounted || ok != true || name.isEmpty) return;
    try {
      if (bot == null) {
        await ApiService().createBot({
          'name': name,
          if (role.isNotEmpty) 'role': role,
          if (prompt.isNotEmpty) 'system_prompt': prompt,
          'temperature': 0.7,
        });
      } else {
        final id = (bot['id'] as num?)?.toInt();
        if (id == null) return;
        await ApiService().updateBot(id, {
          'name': name,
          'role': role.isEmpty ? null : role,
          'system_prompt': prompt.isEmpty ? null : prompt,
        });
      }
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('保存失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _delete(Map<String, dynamic> bot) async {
    final id = (bot['id'] as num?)?.toInt();
    if (id == null) return;
    if (bot['is_default'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('默认角色不能删除')),
      );
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除这个角色？'),
        content: Text('「${bot['name'] ?? ''}」的记忆和会话不会自动删除。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().deleteBot(id);
      if (BotSelectionService().botId == id) {
        await BotSelectionService().clear();
      }
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('删除失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'AI Roles',
              title: 'AI 角色',
              subtitle: '不同的助理，各自的记忆与工具',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建角色',
                  onTap: () => _edit(),
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : _error != null
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _load),
                          ],
                        )
                      : _bots.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.smart_toy_outlined,
                                  title: '还没有 AI 角色',
                                  subtitle: '创建一个写作助手、英语老师或工作助理。',
                                  action: FilledButton.icon(
                                    onPressed: () => _edit(),
                                    icon: const Icon(Icons.add, size: 17),
                                    label: const Text('新建角色'),
                                  ),
                                ),
                              ],
                            )
                          : RefreshIndicator(
                              onRefresh: _load,
                              color: palette.primary,
                              child: ListView.builder(
                                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                                itemCount: _bots.length,
                                itemBuilder: (context, index) {
                                  final bot = _bots[index];
                                  final id = (bot['id'] as num?)?.toInt();
                                  final selected = id == _selectedId;
                                  return Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: AppCard(
                                      onTap: () => _select(bot),
                                      borderColor: selected
                                          ? palette.primary.withValues(alpha: 0.5)
                                          : null,
                                      child: Row(
                                        children: [
                                          CircleAvatar(
                                            radius: 19,
                                            backgroundColor: palette.primarySoft,
                                            child: Icon(
                                              Icons.smart_toy_outlined,
                                              size: 20,
                                              color: palette.primary,
                                            ),
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Row(
                                                  children: [
                                                    Flexible(
                                                      child: Text(
                                                        (bot['name'] ?? 'AI 助理').toString(),
                                                        maxLines: 1,
                                                        overflow: TextOverflow.ellipsis,
                                                        style: TextStyle(
                                                          fontSize: 13,
                                                          fontWeight: FontWeight.w800,
                                                          color: palette.ink,
                                                        ),
                                                      ),
                                                    ),
                                                    if (bot['is_default'] == true) ...[
                                                      const SizedBox(width: 6),
                                                      Container(
                                                        padding: const EdgeInsets.symmetric(
                                                          horizontal: 5,
                                                          vertical: 1,
                                                        ),
                                                        decoration: BoxDecoration(
                                                          color: palette.primarySoft,
                                                          borderRadius: BorderRadius.circular(5),
                                                        ),
                                                        child: Text(
                                                          '默认',
                                                          style: TextStyle(
                                                            fontSize: 9,
                                                            color: palette.primary,
                                                          ),
                                                        ),
                                                      ),
                                                    ],
                                                  ],
                                                ),
                                                const SizedBox(height: 2),
                                                Text(
                                                  (bot['role'] ?? '').toString().isEmpty
                                                      ? (selected ? '当前聊天角色' : '点击切换')
                                                      : bot['role'].toString(),
                                                  maxLines: 1,
                                                  overflow: TextOverflow.ellipsis,
                                                  style: TextStyle(
                                                    fontSize: 10.5,
                                                    color: selected
                                                        ? palette.primary
                                                        : palette.muted,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          PopupMenuButton<String>(
                                            icon: Icon(
                                              Icons.more_horiz,
                                              size: 18,
                                              color: palette.muted,
                                            ),
                                            onSelected: (v) {
                                              if (v == 'edit') _edit(bot);
                                              if (v == 'delete') _delete(bot);
                                            },
                                            itemBuilder: (_) => const [
                                              PopupMenuItem(
                                                value: 'edit',
                                                child: Text('编辑'),
                                              ),
                                              PopupMenuItem(
                                                value: 'delete',
                                                child: Text('删除'),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
            ),
          ],
        ),
      ),
    );
  }
}
