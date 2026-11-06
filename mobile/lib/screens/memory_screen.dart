import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class MemoryScreen extends StatefulWidget {
  const MemoryScreen({super.key});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  List<Map<String, dynamic>> _candidates = [];
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final api = ApiService();
    List<Map<String, dynamic>> candidates = [];
    List<Map<String, dynamic>> records = [];
    try {
      candidates = await api.listMemoryCandidates();
    } catch (_) {}
    try {
      records = await api.listMemoryRecords();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _candidates = candidates;
      _records = records;
      _loading = false;
    });
  }

  Future<void> _act(Future<bool> action, String success) async {
    try {
      final ok = await action;
      if (!mounted) return;
      if (ok) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(success)),
        );
        await _load();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('操作失败，请稍后重试')),
        );
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('网络异常，请稍后重试')),
      );
    }
  }

  String _kindLabel(String kind) {
    return const {
      'fact': '事实',
      'preference': '偏好',
      'commitment': '承诺',
      'relationship': '关系',
      'project': '项目',
    }[kind] ?? kind;
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
              kicker: 'Memory',
              title: '记忆与关于我',
              subtitle: '${_candidates.length} 条待审核 · ${_records.length} 条长期记忆',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: _load,
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  _tabChip(palette, 0, '待审核 ${_candidates.length}'),
                  const SizedBox(width: 6),
                  _tabChip(palette, 1, '长期记忆 ${_records.length}'),
                ],
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _tab == 0 ? _buildCandidates(palette) : _buildRecords(palette),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _tabChip(AppPalette palette, int value, String label) {
    final selected = _tab == value;
    return InkWell(
      onTap: () => setState(() => _tab = value),
      borderRadius: BorderRadius.circular(18),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? palette.primary : palette.card,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: selected ? palette.primary : palette.line),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 10.5,
            fontWeight: FontWeight.w700,
            color: selected ? Colors.white : palette.muted,
          ),
        ),
      ),
    );
  }

  Widget _buildCandidates(AppPalette palette) {
    if (_candidates.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [
          SizedBox(height: 50),
          EmptyState(
            icon: Icons.auto_awesome_outlined,
            title: '没有待审核的记忆',
            subtitle: 'AI 会从对话和重要邮件里提取候选记忆，确认后才会进入长期记忆。',
          ),
        ],
      );
    }
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
      itemCount: _candidates.length,
      itemBuilder: (context, index) {
        final item = _candidates[index];
        final id = item['id'];
        final trust = (item['trust'] ?? 'trusted').toString();
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  (item['content'] ?? '').toString(),
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.65,
                    color: palette.ink,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 5,
                  runSpacing: 5,
                  children: [
                    SourcePill(
                      label: _kindLabel((item['kind'] ?? 'fact').toString()),
                      color: palette.primary,
                    ),
                    SourcePill(
                      label: trust == 'trusted' ? '可信来源' : '外部内容',
                      color: trust == 'trusted' ? palette.success : palette.accent,
                    ),
                    SourcePill(
                      label: '置信度 ${item['confidence'] ?? 0}',
                      color: palette.muted,
                    ),
                  ],
                ),
                const SizedBox(height: 9),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        onPressed: id is int
                            ? () => _act(
                                  ApiService().approveMemory(id),
                                  '已记住',
                                )
                            : null,
                        style: FilledButton.styleFrom(
                          backgroundColor: palette.primary,
                          minimumSize: const Size.fromHeight(36),
                        ),
                        child: const Text('记住'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: id is int
                            ? () => _act(
                                  ApiService().rejectMemory(id),
                                  '已忽略',
                                )
                            : null,
                        style: OutlinedButton.styleFrom(
                          minimumSize: const Size.fromHeight(36),
                          side: BorderSide(color: palette.line),
                          foregroundColor: palette.muted,
                        ),
                        child: const Text('忽略'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildRecords(AppPalette palette) {
    if (_records.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [
          SizedBox(height: 50),
          EmptyState(
            icon: Icons.psychology_outlined,
            title: '还没有长期记忆',
            subtitle: '确认候选记忆后，AI 会在对话里按相关度使用它们。',
          ),
        ],
      );
    }
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
      itemCount: _records.length,
      itemBuilder: (context, index) {
        final item = _records[index];
        final id = item['id'];
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: AppCard(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        (item['content'] ?? '').toString(),
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.65,
                          color: palette.ink,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 5,
                        children: [
                          SourcePill(
                            label: _kindLabel((item['kind'] ?? 'fact').toString()),
                            color: palette.primary,
                          ),
                          SourcePill(
                            label: '重要度 ${item['importance'] ?? 0}',
                            color: palette.muted,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: '遗忘',
                  icon: Icon(
                    Icons.delete_outline_rounded,
                    size: 19,
                    color: palette.muted,
                  ),
                  onPressed: id is int
                      ? () async {
                          final confirmed = await showDialog<bool>(
                            context: context,
                            builder: (context) => AlertDialog(
                              title: const Text('忘掉这条记忆？'),
                              content: const Text('不会删除原始对话或邮件。'),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(context, false),
                                  child: const Text('取消'),
                                ),
                                FilledButton(
                                  onPressed: () => Navigator.pop(context, true),
                                  child: const Text('遗忘'),
                                ),
                              ],
                            ),
                          );
                          if (confirmed == true) {
                            await _act(
                              ApiService().forgetMemory(id),
                              '已遗忘',
                            );
                          }
                        }
                      : null,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
