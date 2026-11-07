import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/loading_state.dart';

/// Read-only DingTalk signal -> local action suggestions. No chat mirroring and
/// no automatic replies; the user explicitly turns a suggestion into a todo.
class DingTalkActionsScreen extends StatefulWidget {
  const DingTalkActionsScreen({super.key});

  @override
  State<DingTalkActionsScreen> createState() => _DingTalkActionsScreenState();
}

class _DingTalkActionsScreenState extends State<DingTalkActionsScreen> {
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  bool _error = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool refresh = false}) async {
    setState(() {
      _loading = _items.isEmpty;
      _error = false;
    });
    try {
      final items = await ApiService().getDingTalkActions(refresh: refresh);
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = true;
      });
    }
  }

  Future<void> _accept(Map<String, dynamic> item) async {
    try {
      await ApiService().createTodoItem({
        'title': (item['title'] ?? '处理钉钉事项').toString(),
        'description': (item['reason'] ?? '').toString(),
        'priority': 1,
      });
      if (!mounted) return;
      setState(() => _items.remove(item));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已创建待办')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建待办失败: $e')),
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
              kicker: 'DingTalk',
              title: '钉钉行动建议',
              subtitle: '只读分析，不代替钉钉回复',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                RoundIconButton(
                  icon: Icons.refresh_rounded,
                  tooltip: '刷新',
                  onTap: () => _load(refresh: true),
                ),
              ],
            ),
            Expanded(
              child: _loading
                  ? const SkeletonList(count: 4)
                  : _error
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            const SizedBox(height: 40),
                            ErrorState(onRetry: _load),
                          ],
                        )
                      : RefreshIndicator(
                          onRefresh: () => _load(refresh: true),
                          color: palette.primary,
                          child: _items.isEmpty
                              ? ListView(
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  children: const [
                                    SizedBox(height: 50),
                                    EmptyState(
                                      icon: Icons.task_alt_rounded,
                                      title: '暂时没有要处理的事',
                                      subtitle: '钉钉未读、日程和待办会在这里汇总成行动建议。',
                                    ),
                                  ],
                                )
                              : ListView.builder(
                                  padding:
                                      const EdgeInsets.fromLTRB(16, 8, 16, 24),
                                  itemCount: _items.length,
                                  itemBuilder: (context, index) {
                                    final item = _items[index];
                                    return Padding(
                                      padding: const EdgeInsets.only(bottom: 9),
                                      child: _actionCard(palette, item),
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

  Widget _actionCard(AppPalette palette, Map<String, dynamic> item) {
    final kind = (item['kind'] ?? 'follow_up').toString();
    final label = switch (kind) {
      'todo' => '待办',
      'meeting' => '会议',
      'review' => '确认',
      _ => '跟进',
    };
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: palette.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w800,
                    color: palette.primary,
                  ),
                ),
              ),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  (item['conversation'] ?? '').toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 10, color: palette.muted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Text(
            (item['title'] ?? '').toString(),
            style: TextStyle(
              fontSize: 14,
              height: 1.4,
              fontWeight: FontWeight.w700,
              color: palette.ink,
            ),
          ),
          if ((item['reason'] ?? '').toString().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              (item['reason'] ?? '').toString(),
              style: TextStyle(
                fontSize: 11,
                height: 1.5,
                color: palette.muted,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              FilledButton.icon(
                onPressed: () => _accept(item),
                icon: const Icon(Icons.add_task_rounded, size: 16),
                label: const Text('建待办'),
                style: FilledButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  textStyle: const TextStyle(fontSize: 11),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: () => setState(() => _items.remove(item)),
                child: const Text('忽略'),
              ),
              const Spacer(),
              Text(
                '来源：钉钉',
                style: TextStyle(fontSize: 9, color: palette.muted),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
