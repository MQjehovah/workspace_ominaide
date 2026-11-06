import 'package:flutter/material.dart';

import '../models/cos_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class BriefScreen extends StatefulWidget {
  const BriefScreen({super.key});

  @override
  State<BriefScreen> createState() => _BriefScreenState();
}

class _BriefScreenState extends State<BriefScreen> {
  DailyBrief? _brief;
  WeeklyReview? _weekly;
  bool _loading = true;
  int _tab = 0;
  bool _error = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = false;
    });
    final api = ApiService();
    DailyBrief? brief;
    WeeklyReview? weekly;
    try {
      brief = await api.getDailyBrief();
    } catch (_) {}
    try {
      weekly = await api.getWeeklyReview();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _brief = brief;
      _weekly = weekly;
      _error = brief == null && weekly == null;
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
              kicker: 'Chief of Staff',
              title: '幕僚长',
              subtitle: _tab == 0 ? '今日简报' : '本周回顾',
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
                  _tabChip(palette, 0, '今日简报'),
                  const SizedBox(width: 6),
                  _tabChip(palette, 1, '本周回顾'),
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
                      child: _error
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                const SizedBox(height: 40),
                                ErrorState(onRetry: _load),
                              ],
                            )
                          : _tab == 0
                              ? _buildDaily(palette)
                              : _buildWeekly(palette),
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
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 6),
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

  Widget _buildWeekly(AppPalette palette) {
    final weekly = _weekly;
    if (weekly == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [
          SizedBox(height: 50),
          EmptyState(
            icon: Icons.insights_outlined,
            title: '还没有周报',
            subtitle: '本周有足够数据后，再刷新试试。',
          ),
        ],
      );
    }
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
      children: [
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${weekly.periodStart} ~ ${weekly.periodEnd}',
                style: TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  color: palette.primary,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                weekly.summary,
                style: TextStyle(
                  fontSize: 13,
                  height: 1.7,
                  color: palette.ink,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  _stat(palette, '${weekly.stats['todos_done'] ?? 0}', '完成待办'),
                  _stat(palette, '${weekly.stats['todos_pending'] ?? 0}', '进行中'),
                  _stat(palette, '${weekly.stats['insight_days'] ?? 0}', '回顾天数'),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _weeklySection(palette, '本周成果', weekly.wins, palette.success),
        _weeklySection(palette, '进行中', weekly.inProgress, palette.primary),
        _weeklySection(palette, '风险', weekly.risks, palette.accent),
        _weeklySection(palette, '下周重点', weekly.nextWeek, palette.primary),
      ],
    );
  }

  Widget _stat(AppPalette palette, String value, String label) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: palette.ink,
            ),
          ),
          Text(
            label,
            style: TextStyle(fontSize: 9.5, color: palette.muted),
          ),
        ],
      ),
    );
  }

  Widget _weeklySection(
    AppPalette palette,
    String title,
    List<String> items,
    Color color,
  ) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                color: color,
              ),
            ),
            const SizedBox(height: 5),
            for (final item in items)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 5),
                      child: TagDot(color: color, size: 4),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        item,
                        style: TextStyle(
                          fontSize: 11.5,
                          height: 1.55,
                          color: palette.ink,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
