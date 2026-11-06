import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Automation center: routine list, templates and natural-language creation.
class AutomationScreen extends StatefulWidget {
  const AutomationScreen({super.key});

  @override
  State<AutomationScreen> createState() => _AutomationScreenState();
}

class _AutomationScreenState extends State<AutomationScreen> {
  Map<String, dynamic> _overview = {};
  List<Map<String, dynamic>> _routines = [];
  int? _botId;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ApiService();
      final bots = await api.listBots();
      final botId = bots.isEmpty ? null : (bots.first['id'] as num).toInt();
      final routines =
          botId == null ? <Map<String, dynamic>>[] : await api.listBotRoutines(botId);
      final overview = await api.automationOverview();
      if (!mounted) return;
      setState(() {
        _botId = botId;
        _routines = routines;
        _overview = overview;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _toggle(Map<String, dynamic> routine, bool enabled) async {
    final botId = _botId;
    if (botId == null) return;
    try {
      await ApiService().updateAutomationRoutine(
        botId,
        (routine['id'] as num).toInt(),
        {'enabled': enabled},
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('更新失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _showCreateMenu() async {
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.auto_awesome, color: palette.primary),
              title: const Text('一句话创建'),
              subtitle: const Text('描述你想让 AI 自动做的事'),
              onTap: () {
                Navigator.pop(ctx);
                _createFromText();
              },
            ),
            ListTile(
              leading: Icon(Icons.dashboard_customize_outlined, color: palette.primary),
              title: const Text('从模板创建'),
              subtitle: const Text('晨间简报、每日回顾、重要事件扫描等'),
              onTap: () {
                Navigator.pop(ctx);
                _showTemplates();
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Future<void> _showTemplates() async {
    List<Map<String, dynamic>> templates;
    try {
      templates = await ApiService().automationTemplates();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('加载模板失败: $e')),
      );
      return;
    }
    if (!mounted) return;
    final palette = AppPalette.of(context);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: palette.card,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            Text(
              '自动化模板',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w800,
                color: palette.ink,
              ),
            ),
            const SizedBox(height: 8),
            for (final t in templates)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text((t['name'] ?? '').toString()),
                subtitle: Text((t['description'] ?? '').toString()),
                trailing: const Icon(Icons.add_circle_outline, size: 20),
                onTap: () async {
                  Navigator.pop(ctx);
                  await _createFromTemplate((t['key'] ?? '').toString());
                },
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _createFromTemplate(String key) async {
    final botId = _botId;
    if (botId == null) return;
    try {
      await ApiService().createAutomationFromTemplate(botId, key);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('自动化已创建')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _createFromText() async {
    final ctl = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('一句话创建自动化'),
        content: TextField(
          controller: ctl,
          autofocus: true,
          maxLines: 4,
          decoration: const InputDecoration(
            hintText: '例如：每天早上 8 点汇总今天的日程和待办，发通知给我',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
            child: const Text('解析'),
          ),
        ],
      ),
    );
    ctl.dispose();
    if (text == null || text.isEmpty || !mounted) return;
    _showParsing(text);
  }

  Future<void> _showParsing(String text) async {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    Map<String, dynamic> draft;
    try {
      draft = await ApiService().parseAutomationRule(text);
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('解析失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
      return;
    }
    if (!mounted) return;
    Navigator.pop(context);
    final palette = AppPalette.of(context);
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认自动化'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                (draft['name'] ?? '新建自动化').toString(),
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _triggerText(draft),
                style: TextStyle(fontSize: 12, color: palette.primary),
              ),
              if ((draft['explanation'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  draft['explanation'].toString(),
                  style: TextStyle(fontSize: 12, height: 1.5, color: palette.muted),
                ),
              ],
              if ((draft['prompt'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(
                  '任务：${draft['prompt']}',
                  style: TextStyle(fontSize: 12, height: 1.5, color: palette.ink),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await _createFromDraft(draft);
            },
            child: const Text('创建'),
          ),
        ],
      ),
    );
  }

  Future<void> _createFromDraft(Map<String, dynamic> draft) async {
    final botId = _botId;
    if (botId == null) return;
    try {
      await ApiService().createAutomationRoutine(botId, {
        'name': draft['name'] ?? '新建自动化',
        'trigger_type': draft['trigger_type'] ?? 'manual',
        'cron_expr': draft['cron_expr'],
        'event_type': draft['event_type'],
        'event_filter': draft['event_filter'],
        'prompt': draft['prompt'],
        'enabled': true,
      });
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('自动化已创建')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  String _triggerText(Map<String, dynamic> routine) {
    final type = (routine['trigger_type'] ?? 'manual').toString();
    if (type == 'cron') {
      final expr = (routine['cron_expr'] ?? '').toString();
      return expr.isEmpty ? '定时触发' : '定时 · $expr';
    }
    if (type == 'event') return '事件 · ${routine['event_type'] ?? ''}';
    return '手动触发';
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
              kicker: 'Automation',
              title: '自动化',
              subtitle: '让 AI 按规则主动做事',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.add_rounded,
                  tooltip: '新建自动化',
                  onTap: _showCreateMenu,
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
                      : RefreshIndicator(
                          onRefresh: _load,
                          color: palette.primary,
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                            children: [
                              _overviewGrid(palette),
                              const SizedBox(height: 14),
                              if (_routines.isEmpty)
                                EmptyState(
                                  icon: Icons.auto_awesome_outlined,
                                  title: '还没有自动化规则',
                                  subtitle: '用一个模板开始，或直接说一句话让 AI 帮你建。',
                                  action: FilledButton.icon(
                                    onPressed: _showCreateMenu,
                                    icon: const Icon(Icons.add, size: 17),
                                    label: const Text('新建自动化'),
                                  ),
                                )
                              else
                                for (final routine in _routines) ...[
                                  _routineCard(palette, routine),
                                  const SizedBox(height: 10),
                                ],
                            ],
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _overviewGrid(AppPalette palette) {
    final items = [
      ('规则', _overview['routines_total'] ?? 0),
      ('启用', _overview['routines_enabled'] ?? 0),
      ('近 7 天运行', _overview['runs_7d'] ?? 0),
      ('待审批', _overview['pending_approvals'] ?? 0),
    ];
    return Row(
      children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) const SizedBox(width: 8),
          Expanded(
            child: AppCard(
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
              child: Column(
                children: [
                  Text(
                    '${items[i].$2}',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                      color: palette.ink,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    items[i].$1,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 9.5, color: palette.muted),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _routineCard(AppPalette palette, Map<String, dynamic> routine) {
    final enabled = routine['enabled'] == true;
    final status = (routine['last_status'] ?? '').toString();
    return AppCard(
      child: InkWell(
        onTap: () => _openRoutine(routine),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: palette.primarySoft,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  routine['trigger_type'] == 'event'
                      ? Icons.bolt_outlined
                      : Icons.schedule_outlined,
                  size: 19,
                  color: palette.primary,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      (routine['name'] ?? '未命名').toString(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: palette.ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _triggerText(routine),
                      style: TextStyle(fontSize: 10.5, color: palette.muted),
                    ),
                    if (status.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        '上次：$status',
                        style: TextStyle(
                          fontSize: 10,
                          color: status == 'success'
                              ? palette.success
                              : palette.accent,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Switch(
                value: enabled,
                onChanged: (v) => _toggle(routine, v),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openRoutine(Map<String, dynamic> routine) async {
    final botId = _botId;
    final routineId = (routine['id'] as num?)?.toInt();
    if (botId == null || routineId == null) return;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AutomationRoutineScreen(
          botId: botId,
          routineId: routineId,
          initial: routine,
        ),
      ),
    );
    if (mounted) _load();
  }
}

class AutomationRoutineScreen extends StatefulWidget {
  const AutomationRoutineScreen({
    super.key,
    required this.botId,
    required this.routineId,
    this.initial,
  });

  final int botId;
  final int routineId;
  final Map<String, dynamic>? initial;

  @override
  State<AutomationRoutineScreen> createState() => _AutomationRoutineScreenState();
}

class _AutomationRoutineScreenState extends State<AutomationRoutineScreen> {
  Map<String, dynamic> _routine = {};
  Map<String, dynamic> _stats = {};
  List<Map<String, dynamic>> _runs = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _routine = Map<String, dynamic>.from(widget.initial ?? const {});
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ApiService();
      final results = await Future.wait([
        api.automationRoutine(widget.routineId),
        api.automationStats(widget.routineId),
        api.automationRuns(widget.routineId),
      ]);
      if (!mounted) return;
      setState(() {
        _routine = results[0] as Map<String, dynamic>;
        _stats = results[1] as Map<String, dynamic>;
        _runs = results[2] as List<Map<String, dynamic>>;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _dryRun() async {
    try {
      final result = await ApiService().dryRunAutomationRoutine(widget.routineId);
      if (!mounted) return;
      final plan = (result['plan'] ?? result['result'] ?? result).toString();
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('试运行计划'),
          content: SingleChildScrollView(child: Text(plan)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('知道了'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('试运行失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _runNow() async {
    try {
      await ApiService().runAutomationRoutineNow(widget.botId, widget.routineId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已触发运行')),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('运行失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _toggle(bool enabled) async {
    try {
      await ApiService().updateAutomationRoutine(
        widget.botId,
        widget.routineId,
        {'enabled': enabled},
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('更新失败: $e')),
      );
    }
  }

  Future<void> _edit() async {
    final nameCtl = TextEditingController(text: (_routine['name'] ?? '').toString());
    final cronCtl = TextEditingController(text: (_routine['cron_expr'] ?? '').toString());
    final eventCtl = TextEditingController(text: (_routine['event_type'] ?? '').toString());
    final promptCtl = TextEditingController(text: (_routine['prompt'] ?? '').toString());
    var trigger = (_routine['trigger_type'] ?? 'cron').toString();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('编辑自动化'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameCtl,
                  decoration: const InputDecoration(labelText: '名称'),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: trigger,
                  decoration: const InputDecoration(labelText: '触发方式'),
                  items: const [
                    DropdownMenuItem(value: 'cron', child: Text('定时')),
                    DropdownMenuItem(value: 'event', child: Text('事件')),
                    DropdownMenuItem(value: 'manual', child: Text('手动')),
                  ],
                  onChanged: (v) => setDialogState(() => trigger = v ?? 'cron'),
                ),
                if (trigger == 'cron') ...[
                  const SizedBox(height: 10),
                  TextField(
                    controller: cronCtl,
                    decoration: const InputDecoration(
                      labelText: 'cron 表达式',
                      hintText: '0 8 * * *',
                    ),
                  ),
                ],
                if (trigger == 'event') ...[
                  const SizedBox(height: 10),
                  TextField(
                    controller: eventCtl,
                    decoration: const InputDecoration(
                      labelText: '事件类型',
                      hintText: 'file.uploaded / mail.received / todo.completed',
                    ),
                  ),
                ],
                const SizedBox(height: 10),
                TextField(
                  controller: promptCtl,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(labelText: '任务说明'),
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
      ),
    );
    final name = nameCtl.text.trim();
    final cron = cronCtl.text.trim();
    final event = eventCtl.text.trim();
    final prompt = promptCtl.text.trim();
    nameCtl.dispose();
    cronCtl.dispose();
    eventCtl.dispose();
    promptCtl.dispose();
    if (!mounted || ok != true || name.isEmpty) return;
    try {
      await ApiService().updateAutomationRoutine(
        widget.botId,
        widget.routineId,
        {
          'name': name,
          'trigger_type': trigger,
          'cron_expr': trigger == 'cron' && cron.isNotEmpty ? cron : null,
          'event_type': trigger == 'event' && event.isNotEmpty ? event : null,
          'prompt': prompt.isEmpty ? null : prompt,
        },
      );
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已保存')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('保存失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除自动化？'),
        content: const Text('删除后不会影响已经产生的运行记录。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService().deleteAutomationRoutine(widget.botId, widget.routineId);
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('删除失败: $e')),
      );
    }
  }

  String _triggerText() {
    final type = (_routine['trigger_type'] ?? 'manual').toString();
    if (type == 'cron') {
      final expr = (_routine['cron_expr'] ?? '').toString();
      return expr.isEmpty ? '定时触发' : '定时 · $expr';
    }
    if (type == 'event') return '事件 · ${_routine['event_type'] ?? ''}';
    return '手动触发';
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final enabled = _routine['enabled'] == true;
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Automation',
              title: (_routine['name'] ?? '自动化').toString(),
              subtitle: _triggerText(),
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                PopupMenuButton<String>(
                  icon: Icon(Icons.more_horiz, color: palette.muted),
                  onSelected: (v) {
                    if (v == 'edit') _edit();
                    if (v == 'delete') _delete();
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 'edit', child: Text('编辑')),
                    PopupMenuItem(value: 'delete', child: Text('删除')),
                  ],
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
                      : RefreshIndicator(
                          onRefresh: _load,
                          color: palette.primary,
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                            children: [
                              AppCard(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Expanded(
                                          child: Text(
                                            enabled ? '已启用' : '已暂停',
                                            style: TextStyle(
                                              fontSize: 12,
                                              fontWeight: FontWeight.w700,
                                              color: enabled
                                                  ? palette.success
                                                  : palette.muted,
                                            ),
                                          ),
                                        ),
                                        Switch(value: enabled, onChanged: _toggle),
                                      ],
                                    ),
                                    if ((_routine['next_run_at'] ?? '').toString().isNotEmpty)
                                      Text(
                                        '下次：${_fmtTime(_routine['next_run_at'])}',
                                        style: TextStyle(fontSize: 11, color: palette.muted),
                                      ),
                                    const SizedBox(height: 10),
                                    Row(
                                      children: [
                                        Expanded(
                                          child: OutlinedButton.icon(
                                            onPressed: _dryRun,
                                            icon: const Icon(Icons.science_outlined, size: 16),
                                            label: const Text('试运行'),
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: FilledButton.icon(
                                            onPressed: _runNow,
                                            icon: const Icon(Icons.play_arrow_rounded, size: 18),
                                            label: const Text('立即运行'),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 12),
                              _statsCard(palette),
                              if ((_routine['prompt'] ?? '').toString().isNotEmpty) ...[
                                const SizedBox(height: 12),
                                AppCard(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        '任务说明',
                                        style: TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.w800,
                                          color: palette.muted,
                                        ),
                                      ),
                                      const SizedBox(height: 6),
                                      Text(
                                        _routine['prompt'].toString(),
                                        style: TextStyle(
                                          fontSize: 12,
                                          height: 1.6,
                                          color: palette.ink,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                              const SizedBox(height: 16),
                              Text(
                                '最近运行',
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w800,
                                  color: palette.ink,
                                ),
                              ),
                              const SizedBox(height: 6),
                              if (_runs.isEmpty)
                                Text(
                                  '还没有运行记录。',
                                  style: TextStyle(fontSize: 11, color: palette.muted),
                                )
                              else
                                for (final run in _runs)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: _runTile(palette, run),
                                  ),
                            ],
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statsCard(AppPalette palette) {
    final total = (_stats['total'] ?? 0).toString();
    final byStatus = _stats['by_status'] is Map ? _stats['by_status'] as Map : const {};
    return AppCard(
      child: Row(
        children: [
          Expanded(child: _stat(palette, '近 30 天', total)),
          Expanded(child: _stat(palette, '成功', '${byStatus['success'] ?? 0}')),
          Expanded(child: _stat(palette, '失败', '${byStatus['failed'] ?? byStatus['error'] ?? 0}')),
        ],
      ),
    );
  }

  Widget _stat(AppPalette palette, String label, String value) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w800,
            color: palette.ink,
          ),
        ),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(fontSize: 9.5, color: palette.muted)),
      ],
    );
  }

  Widget _runTile(AppPalette palette, Map<String, dynamic> run) {
    final status = (run['status'] ?? '').toString();
    final ok = status == 'success' || status == 'completed';
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(
        children: [
          Icon(
            ok ? Icons.check_circle_outline : Icons.error_outline,
            size: 17,
            color: ok ? palette.success : palette.accent,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              (run['trigger'] ?? status).toString(),
              style: TextStyle(fontSize: 11.5, color: palette.ink),
            ),
          ),
          Text(
            _fmtTime(run['created_at']),
            style: TextStyle(fontSize: 10, color: palette.muted),
          ),
        ],
      ),
    );
  }

  String _fmtTime(dynamic raw) {
    final d = DateTime.tryParse((raw ?? '').toString());
    if (d == null) return '';
    final local = d.toLocal();
    return '${local.month}/${local.day} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }
}
