import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class GoalsScreen extends StatefulWidget {
  const GoalsScreen({super.key});

  @override
  State<GoalsScreen> createState() => _GoalsScreenState();
}

class _GoalsScreenState extends State<GoalsScreen> {
  final _title = TextEditingController();
  final _description = TextEditingController();
  List<Map<String, dynamic>> _goals = [];
  List<Map<String, dynamic>> _tasks = [];
  Map<String, dynamic>? _selected;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final rows = await ApiService().listGoals();
    if (!mounted) return;
    setState(() {
      _goals = rows;
      _loading = false;
    });
  }

  Future<void> _select(Map<String, dynamic> goal) async {
    final id = goal['id'];
    if (id is! int) return;
    final tasks = await ApiService().listGoalTasks(id);
    if (!mounted) return;
    setState(() {
      _selected = goal;
      _tasks = tasks;
    });
  }

  Future<void> _create() async {
    if (_title.text.trim().isEmpty) return;
    final goal = await ApiService().createGoal(
      title: _title.text.trim(),
      description: _description.text.trim(),
    );
    if (!mounted || goal == null) return;
    _title.clear();
    _description.clear();
    await _load();
    await _select(goal);
  }

  Future<void> _plan() async {
    final id = _selected?['id'];
    if (id is! int) return;
    await ApiService().planGoal(id);
    await _load();
    await _select(_selected!);
  }

  Future<void> _tick() async {
    final id = _selected?['id'];
    if (id is! int) return;
    final result = await ApiService().tickGoal(id);
    if (!mounted) return;
    if (result != null) {
      setState(() {
        _selected = result['goal'] is Map
            ? Map<String, dynamic>.from(result['goal'] as Map)
            : _selected;
        _tasks = (result['tasks'] as List? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      });
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('目标'),
        backgroundColor: palette.background,
        foregroundColor: palette.ink,
      ),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  children: [
                    AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          TextField(
                            controller: _title,
                            decoration: const InputDecoration(
                              labelText: '目标',
                              hintText: '例如：周五前拿到预算确认',
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _description,
                            decoration: const InputDecoration(labelText: '背景（可选）'),
                          ),
                          const SizedBox(height: 8),
                          Align(
                            alignment: Alignment.centerRight,
                            child: FilledButton(
                              onPressed: _create,
                              child: const Text('创建目标'),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_goals.isEmpty)
                      AppCard(
                        child: Text(
                          '还没有目标。把持续想做的事写下来，Bot 会拆成任务并跟进。',
                          style: TextStyle(color: palette.muted),
                        ),
                      ),
                    for (final goal in _goals)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: GestureDetector(
                          onTap: () => _select(goal),
                          child: AppCard(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  (goal['title'] ?? '').toString(),
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w800,
                                    color: palette.ink,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '${goal['status']} · 工作区 ${goal['workspace_id'] ?? '-'}',
                                  style: TextStyle(fontSize: 11, color: palette.muted),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    if (_selected != null) ...[
                      const SizedBox(height: 8),
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '任务',
                                    style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      color: palette.ink,
                                    ),
                                  ),
                                ),
                                TextButton(onPressed: _plan, child: const Text('规划')),
                                const SizedBox(width: 4),
                                FilledButton(onPressed: _tick, child: const Text('推进')),
                              ],
                            ),
                            for (final task in _tasks)
                              Padding(
                                padding: const EdgeInsets.only(top: 6),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        (task['title'] ?? '').toString(),
                                        style: TextStyle(fontSize: 12, color: palette.ink),
                                      ),
                                    ),
                                    Text(
                                      '${task['agent_profile_key'] ?? ''} · ${task['status']}',
                                      style: TextStyle(fontSize: 10, color: palette.muted),
                                    ),
                                  ],
                                ),
                              ),
                            if (_tasks.isEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 6),
                                child: Text(
                                  '还没有任务，点「规划」。',
                                  style: TextStyle(fontSize: 11, color: palette.muted),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }
}
