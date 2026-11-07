import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Per-bot Agent Skills toggles. Skill content lives on disk (SKILL.md).
class BotSkillsScreen extends StatefulWidget {
  const BotSkillsScreen({
    super.key,
    required this.botId,
    required this.botName,
  });

  final int botId;
  final String botName;

  @override
  State<BotSkillsScreen> createState() => _BotSkillsScreenState();
}

class _BotSkillsScreenState extends State<BotSkillsScreen> {
  List<Map<String, dynamic>> _skills = [];
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
      final skills = await ApiService().listBotSkills(widget.botId);
      if (!mounted) return;
      setState(() {
        _skills = skills;
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

  Future<void> _toggle(Map<String, dynamic> skill, bool enabled) async {
    final key = (skill['key'] ?? '').toString();
    if (key.isEmpty) return;
    setState(() {
      skill['enabled'] = enabled;
    });
    try {
      await ApiService().setBotSkill(widget.botId, key, enabled);
    } catch (e) {
      if (!mounted) return;
      setState(() => skill['enabled'] = !enabled);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('保存失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  IconData _icon(String key) {
    if (key == 'daily-brief') return Icons.insights_outlined;
    if (key == 'meeting-prepare') return Icons.event_note_outlined;
    if (key == 'weekly-review') return Icons.calendar_view_week_outlined;
    return Icons.extension_outlined;
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
              kicker: 'Skills',
              title: widget.botName,
              subtitle: 'Agent Skills · 默认全开',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
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
                                child: Text(
                                  '技能是 Bot 的高层能力，例如“每日简报”“会议准备”。'
                                  '关闭后该 Bot 不再使用这个技能；聊天、工作台和快捷入口都会遵守这个开关。',
                                  style: TextStyle(
                                    fontSize: 11,
                                    height: 1.6,
                                    color: palette.muted,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 12),
                              for (final skill in _skills) ...[
                                AppCard(
                                  child: Row(
                                    children: [
                                      Container(
                                        width: 38,
                                        height: 38,
                                        decoration: BoxDecoration(
                                          color: palette.primarySoft,
                                          borderRadius: BorderRadius.circular(11),
                                        ),
                                        child: Icon(
                                          _icon((skill['key'] ?? '').toString()),
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
                                              (skill['name'] ?? '').toString(),
                                              style: TextStyle(
                                                fontSize: 13,
                                                fontWeight: FontWeight.w800,
                                                color: palette.ink,
                                              ),
                                            ),
                                            const SizedBox(height: 2),
                                            Text(
                                              (skill['description'] ?? '').toString(),
                                              style: TextStyle(
                                                fontSize: 10.5,
                                                height: 1.45,
                                                color: palette.muted,
                                              ),
                                            ),
                                            const SizedBox(height: 3),
                                            Text(
                                              (skill['key'] ?? '').toString(),
                                              style: TextStyle(
                                                fontSize: 9.5,
                                                color: palette.muted,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      Switch(
                                        value: skill['enabled'] != false,
                                        onChanged: (v) => _toggle(skill, v),
                                      ),
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 8),
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
}
