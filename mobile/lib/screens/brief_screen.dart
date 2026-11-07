import 'package:flutter/material.dart';

import '../models/cos_models.dart';
import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class BriefScreen extends StatefulWidget {
  const BriefScreen({super.key});

  @override
  State<BriefScreen> createState() => _BriefScreenState();
}

class _BriefScreenState extends State<BriefScreen> {
  DailyBrief? _brief;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    DailyBrief? brief;
    try {
      brief = await ApiService().getDailyBrief(
        botId: BotSelectionService().botId,
      );
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _brief = brief;
      _loading = false;
    });
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
              kicker: 'Briefing',
              title: '简报',
              subtitle: '今日简报',
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
            const SizedBox(height: 4),
            Expanded(
              child: _loading
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _brief == null
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                ErrorState(onRetry: _load),
                              ],
                            )
                          : _buildDaily(palette),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDaily(AppPalette palette) {
    final brief = _brief;
    if (brief == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [
          SizedBox(height: 50),
          EmptyState(
            icon: Icons.auto_awesome_outlined,
            title: '还没有今日简报',
            subtitle: '确认日程、待办或邮件后，再刷新试试。',
          ),
        ],
      );
    }
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
      children: [
        AppCard(
          color: palette.primarySoft,
          borderColor: Colors.transparent,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.auto_awesome, size: 15, color: palette.primary),
                  const SizedBox(width: 5),
                  Text(
                    '今日焦点',
                    style: TextStyle(
                      fontSize: 10,
                      letterSpacing: 1,
                      fontWeight: FontWeight.w700,
                      color: palette.primary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 7),
              Text(
                brief.summary.isEmpty ? '今天没有需要特别处理的事项。' : brief.summary,
                style: TextStyle(
                  fontSize: 13,
                  height: 1.7,
                  color: palette.ink,
                ),
              ),
              if (brief.focus.isNotEmpty) ...[
                const SizedBox(height: 9),
                Wrap(
                  spacing: 5,
                  runSpacing: 5,
                  children: [
                    for (final item in brief.focus)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: palette.card,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: palette.line),
                        ),
                        child: Text(
                          item,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: palette.primary,
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 10),
        for (final section in brief.sections)
          if (section.items.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          section.title,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            color: palette.ink,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          '${section.items.length}',
                          style: TextStyle(fontSize: 10, color: palette.muted),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    for (final item in section.items)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item.title,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: palette.ink,
                              ),
                            ),
                            if (item.summary.isNotEmpty)
                              Text(
                                item.summary,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 10.5,
                                  height: 1.5,
                                  color: palette.muted,
                                ),
                              ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
      ],
    );
  }

}
