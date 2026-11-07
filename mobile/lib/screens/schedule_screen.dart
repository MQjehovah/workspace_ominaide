import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/event_time.dart';
import '../services/local_cache_service.dart';
import '../services/local_reminder_service.dart';
import '../theme/app_theme.dart';
import '../widgets/loading_state.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});
  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  List<Map<String, dynamic>> _events = [];
  List<Map<String, dynamic>> _weekEvents = [];
  List<Map<String, dynamic>> _dayEvents = [];
  List<Map<String, dynamic>> _monthEvents = [];
  bool _loading = true;
  bool _viewLoading = false;
  String _view = 'list';
  String _error = '';
  late DateTime _weekStart = _monday(DateTime.now());
  late DateTime _focusedDay = DateTime.now();
  late DateTime _monthStart =
      DateTime(DateTime.now().year, DateTime.now().month, 1);

  static DateTime _monday(DateTime date) {
    final day = DateTime(date.year, date.month, date.day);
    return day.subtract(Duration(days: day.weekday - 1));
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _loadDay() async {
    setState(() => _viewLoading = true);
    try {
      final start = DateTime(
        _focusedDay.year,
        _focusedDay.month,
        _focusedDay.day,
      );
      final events = await ApiService().listScheduleEvents(
        start: start.toIso8601String(),
        end: start.add(const Duration(days: 1)).toIso8601String(),
      );
      if (!mounted) return;
      setState(() {
        _dayEvents = events;
        _viewLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _viewLoading = false);
    }
  }

  Future<void> _loadMonth() async {
    setState(() => _viewLoading = true);
    try {
      final gridStart = _monday(_monthStart);
      final events = await ApiService().listScheduleEvents(
        start: gridStart.toIso8601String(),
        end: gridStart.add(const Duration(days: 42)).toIso8601String(),
      );
      if (!mounted) return;
      setState(() {
        _monthEvents = events;
        _viewLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _viewLoading = false);
    }
  }

  Future<void> _loadWeek() async {
    setState(() => _viewLoading = true);
    try {
      final events = await ApiService().listScheduleEvents(
        start: _weekStart.toIso8601String(),
        end: _weekStart.add(const Duration(days: 7)).toIso8601String(),
      );
      if (!mounted) return;
      setState(() {
        _weekEvents = events;
        _viewLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _viewLoading = false);
    }
  }

  void _switchView(String view) {
    setState(() => _view = view);
    _refreshCurrentView();
  }

  void _refreshCurrentView() {
    if (_view == 'day') {
      _loadDay();
    } else if (_view == 'week') {
      _loadWeek();
    } else if (_view == 'month') {
      _loadMonth();
    } else {
      _load();
    }
  }

  void _shiftWeek(int days) {
    setState(() => _weekStart = _weekStart.add(Duration(days: days)));
    _loadWeek();
  }

  void _shiftDay(int days) {
    setState(() => _focusedDay = _focusedDay.add(Duration(days: days)));
    _loadDay();
  }

  void _shiftMonth(int months) {
    final next = DateTime(_monthStart.year, _monthStart.month + months, 1);
    setState(() => _monthStart = next);
    _loadMonth();
  }

  void _goToday() {
    final now = DateTime.now();
    setState(() {
      _weekStart = _monday(now);
      _focusedDay = now;
      _monthStart = DateTime(now.year, now.month, 1);
    });
    _refreshCurrentView();
  }

  Future<void> _load() async {
    setState(() {
      _loading = _events.isEmpty;
      _error = '';
    });
    if (_events.isEmpty) {
      final cached = await LocalCacheService().readList('schedule');
      if (mounted && cached.isNotEmpty) {
        setState(() {
          _events = cached;
          _loading = false;
        });
      }
    }
    try {
      final now = DateTime.now();
      final start = DateTime(now.year, now.month, now.day);
      final events = await ApiService().listScheduleEvents(
        start: start.toIso8601String(),
      );
      if (!mounted) return;
      setState(() {
        _events = events;
        _loading = false;
      });
      await LocalCacheService().writeJson('schedule', events);
      LocalReminderService().syncSchedule(events);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (_events.isEmpty) _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _add() async {
    final titleCtl = TextEditingController();
    var selected = DateTime.now().add(const Duration(hours: 1));
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('新建日程'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: titleCtl,
                decoration: const InputDecoration(labelText: '标题'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final picked = await _pickDateTime(c, selected);
                  if (picked == null) return;
                  setDialogState(() => selected = picked);
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text('时间：${_fmtDateTime(selected)}'),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(c, false),
                child: const Text('取消')),
            TextButton(
                onPressed: () => Navigator.pop(c, true),
                child: const Text('创建')),
          ],
        ),
      ),
    );
    final title = titleCtl.text.trim();
    titleCtl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().createScheduleEvent({
        'title': title,
        'start_time': selected.toUtc().toIso8601String(),
        'end_time':
            selected.add(const Duration(hours: 1)).toUtc().toIso8601String(),
      });
      if (!mounted) return;
      _refreshCurrentView();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('创建失败: $e')));
    }
  }

  Future<DateTime?> _pickDateTime(
      BuildContext context, DateTime initial) async {
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
    );
    if (date == null || !context.mounted) return null;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null) return null;
    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  Future<void> _edit(Map<String, dynamic> event) async {
    final id = (event['id'] as num?)?.toInt();
    if (id == null) return;
    final titleCtl =
        TextEditingController(text: (event['title'] ?? '').toString());
    var selected = DateTime.tryParse((event['start_time'] ?? '').toString()) ??
        DateTime.now().add(const Duration(hours: 1));
    if (selected.isUtc) selected = selected.toLocal();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setDialogState) => AlertDialog(
          title: const Text('编辑日程'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: titleCtl,
                decoration: const InputDecoration(labelText: '标题'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final picked = await _pickDateTime(c, selected);
                  if (picked == null) return;
                  setDialogState(() => selected = picked);
                },
                icon: const Icon(Icons.event_outlined, size: 16),
                label: Text('时间：${_fmtDateTime(selected)}'),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(c, false),
                child: const Text('取消')),
            TextButton(
                onPressed: () => Navigator.pop(c, true),
                child: const Text('保存')),
          ],
        ),
      ),
    );
    final title = titleCtl.text.trim();
    titleCtl.dispose();
    if (!mounted || ok != true || title.isEmpty) return;
    try {
      await ApiService().updateScheduleEvent(id, {
        'title': title,
        'start_time': selected.toUtc().toIso8601String(),
        'end_time':
            selected.add(const Duration(hours: 1)).toUtc().toIso8601String(),
      });
      if (!mounted) return;
      _refreshCurrentView();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('保存失败: $e')));
    }
  }

  String _fmtDateTime(DateTime d) {
    final h = d.hour.toString().padLeft(2, '0');
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.month}月${d.day}日 $h:$m';
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final now = DateTime.now();
    final active = _events.where((event) => !eventHasEnded(event, now)).toList()
      ..sort(_compareByStart);
    final ended = _events.where((event) => eventHasEnded(event, now)).toList()
      ..sort(_compareByEndDesc);
    return Scaffold(
      appBar: AppBar(
        title: const Text('日程'),
        actions: [
          IconButton(onPressed: _add, icon: const Icon(Icons.add)),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 38,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 1),
              children: [
                _viewChip('列表', 'list', palette),
                const SizedBox(width: 6),
                _viewChip('日', 'day', palette),
                const SizedBox(width: 6),
                _viewChip('周', 'week', palette),
                const SizedBox(width: 6),
                _viewChip('月', 'month', palette),
              ],
            ),
          ),
          Expanded(child: _buildCurrentView(palette, active, ended)),
        ],
      ),
    );
  }

  Widget _viewChip(String label, String value, AppPalette palette) {
    final selected = _view == value;
    return InkWell(
      onTap: () => _switchView(value),
      borderRadius: BorderRadius.circular(18),
      child: Container(
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? palette.primary : palette.card,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: selected ? palette.primary : palette.line,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: selected ? Colors.white : palette.muted,
          ),
        ),
      ),
    );
  }

  Widget _buildCurrentView(
    AppPalette palette,
    List<Map<String, dynamic>> active,
    List<Map<String, dynamic>> ended,
  ) {
    return switch (_view) {
      'day' => _buildDayView(palette),
      'week' => _buildWeekView(palette),
      'month' => _buildMonthView(palette),
      _ => _loading
          ? const SkeletonList(count: 5)
          : _error.isNotEmpty
              ? Center(
                  child: Text(
                    _error,
                    style: const TextStyle(color: Colors.red),
                  ),
                )
              : _events.isEmpty
                  ? const Center(child: Text('暂无日程'))
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 8,
                        ),
                        children: [
                          if (active.isNotEmpty) ...[
                            _sectionTitle(
                              '待开始 / 进行中',
                              active.length,
                              palette,
                            ),
                            for (final event in active)
                              _eventCard(event, ended: false, palette: palette),
                          ],
                          if (ended.isNotEmpty) ...[
                            if (active.isNotEmpty) const SizedBox(height: 8),
                            _sectionTitle('已结束', ended.length, palette),
                            for (final event in ended)
                              _eventCard(event, ended: true, palette: palette),
                          ],
                        ],
                      ),
                    ),
    };
  }

  Widget _buildDayView(AppPalette palette) {
    const hourHeight = 64.0;
    final now = DateTime.now();
    final dayStart = DateTime(
      _focusedDay.year,
      _focusedDay.month,
      _focusedDay.day,
    );
    final dayEnd = dayStart.add(const Duration(days: 1));
    final events = _dayEvents;
    const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 2, 8, 2),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left_rounded),
                onPressed: () => _shiftDay(-1),
              ),
              Expanded(
                child: Text(
                  '${_focusedDay.month}月${_focusedDay.day}日 周${weekdays[_focusedDay.weekday - 1]}',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
              ),
              TextButton(onPressed: _goToday, child: const Text('今天')),
              IconButton(
                icon: const Icon(Icons.chevron_right_rounded),
                onPressed: () => _shiftDay(1),
              ),
            ],
          ),
        ),
        if (_viewLoading)
          LinearProgressIndicator(
            color: palette.primary,
            backgroundColor: palette.primarySoft,
          ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: 20),
            child: SizedBox(
              height: 24 * hourHeight,
              child: Stack(
                children: [
                  for (var hour = 0; hour < 24; hour++)
                    Positioned(
                      top: hour * hourHeight,
                      left: 0,
                      right: 0,
                      height: hourHeight,
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(
                            width: 44,
                            child: Padding(
                              padding: const EdgeInsets.only(top: 2, right: 4),
                              child: Text(
                                '${hour.toString().padLeft(2, '0')}:00',
                                textAlign: TextAlign.right,
                                style: TextStyle(
                                  fontSize: 8.5,
                                  color: palette.muted,
                                ),
                              ),
                            ),
                          ),
                          Expanded(
                            child: Container(
                              decoration: BoxDecoration(
                                border: Border(
                                  top: BorderSide(
                                    color: palette.line.withValues(alpha: 0.55),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  for (final event in events)
                    _dayEvent(
                      event,
                      dayStart,
                      dayEnd,
                      palette,
                      hourHeight,
                    ),
                  if (_isSameDay(_focusedDay, now))
                    Positioned(
                      top: (now.hour + now.minute / 60) * hourHeight,
                      left: 44,
                      right: 0,
                      child: Container(height: 1.5, color: palette.accent),
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _dayEvent(
    Map<String, dynamic> event,
    DateTime dayStart,
    DateTime dayEnd,
    AppPalette palette,
    double hourHeight,
  ) {
    final start = eventStart(event);
    final end = eventEnd(event);
    if (start == null || end == null) return const SizedBox.shrink();
    final visibleStart = start.isBefore(dayStart) ? dayStart : start;
    final visibleEnd = end.isAfter(dayEnd) ? dayEnd : end;
    final top = (visibleStart.hour + visibleStart.minute / 60) * hourHeight;
    final height =
        ((visibleEnd.difference(visibleStart).inMinutes / 60) * hourHeight)
            .clamp(26.0, 24 * hourHeight);
    final clock =
        '${start.hour.toString().padLeft(2, '0')}:${start.minute.toString().padLeft(2, '0')}'
        '-${end.hour.toString().padLeft(2, '0')}:${end.minute.toString().padLeft(2, '0')}';
    return Positioned(
      top: top,
      left: 48,
      right: 8,
      height: height,
      child: GestureDetector(
        onTap: () => _edit(event),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: palette.primarySoft,
            borderRadius: BorderRadius.circular(9),
            border: Border(
              left: BorderSide(color: palette.primary, width: 3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                clock,
                style: TextStyle(
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  color: palette.primary,
                ),
              ),
              Text(
                (event['title'] ?? '日程').toString(),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: palette.ink,
                ),
              ),
              if ((event['notes'] ?? '').toString().isNotEmpty)
                Text(
                  (event['notes'] ?? '').toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 9, color: palette.muted),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMonthView(AppPalette palette) {
    final now = DateTime.now();
    final gridStart = _monday(_monthStart);
    final days = [
      for (var i = 0; i < 42; i++) gridStart.add(Duration(days: i)),
    ];
    const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 2, 8, 2),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left_rounded),
                onPressed: () => _shiftMonth(-1),
              ),
              Expanded(
                child: Text(
                  '${_monthStart.year}年${_monthStart.month}月',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
              ),
              TextButton(onPressed: _goToday, child: const Text('今天')),
              IconButton(
                icon: const Icon(Icons.chevron_right_rounded),
                onPressed: () => _shiftMonth(1),
              ),
            ],
          ),
        ),
        if (_viewLoading)
          LinearProgressIndicator(
            color: palette.primary,
            backgroundColor: palette.primarySoft,
          ),
        Row(
          children: [
            for (final label in weekdays)
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text(
                    label,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 9, color: palette.muted),
                  ),
                ),
              ),
          ],
        ),
        Expanded(
          child: Column(
            children: [
              for (var row = 0; row < 6; row++)
                Expanded(
                  child: Row(
                    children: [
                      for (var col = 0; col < 7; col++)
                        Expanded(
                          child: _monthCell(
                            days[row * 7 + col],
                            palette,
                            now,
                          ),
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _monthCell(DateTime day, AppPalette palette, DateTime now) {
    final inMonth = day.month == _monthStart.month;
    final isToday = _isSameDay(day, now);
    final dayEvents = _monthEvents.where((event) {
      final start = eventStart(event);
      if (start == null) return false;
      return _isSameDay(start, day);
    }).toList();
    return InkWell(
      onTap: () {
        setState(() {
          _focusedDay = day;
          _view = 'day';
        });
        _loadDay();
      },
      child: Container(
        margin: const EdgeInsets.all(1),
        padding: const EdgeInsets.fromLTRB(2, 2, 2, 1),
        decoration: BoxDecoration(
          color: inMonth ? palette.card : palette.background,
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: palette.line.withValues(alpha: 0.6)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 20,
                height: 20,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: isToday ? palette.primary : Colors.transparent,
                  shape: BoxShape.circle,
                ),
                child: Text(
                  '${day.day}',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: isToday
                        ? Colors.white
                        : inMonth
                            ? palette.ink
                            : palette.muted,
                  ),
                ),
              ),
            ),
            for (final event in dayEvents.take(2))
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Row(
                  children: [
                    Container(
                      width: 3,
                      height: 3,
                      decoration: BoxDecoration(
                        color: palette.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 2),
                    Expanded(
                      child: Text(
                        (event['title'] ?? '').toString(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 6.5,
                          height: 1.2,
                          color: palette.primary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            if (dayEvents.length > 2)
              Text(
                '+${dayEvents.length - 2}',
                style: TextStyle(fontSize: 6, color: palette.muted),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildWeekView(AppPalette palette) {
    const hourHeight = 56.0;
    final now = DateTime.now();
    final days = [
      for (var i = 0; i < 7; i++) _weekStart.add(Duration(days: i)),
    ];
    const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    final title =
        '${_weekStart.month}月${_weekStart.day}日 - ${_weekStart.add(const Duration(days: 6)).month}月${_weekStart.add(const Duration(days: 6)).day}日';

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 4, 8, 2),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left_rounded),
                onPressed: () => _shiftWeek(-7),
              ),
              Expanded(
                child: Text(
                  title,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: palette.ink,
                  ),
                ),
              ),
              TextButton(onPressed: _goToday, child: const Text('今天')),
              IconButton(
                icon: const Icon(Icons.chevron_right_rounded),
                onPressed: () => _shiftWeek(7),
              ),
            ],
          ),
        ),
        Row(
          children: [
            const SizedBox(width: 38),
            for (var i = 0; i < 7; i++)
              Expanded(
                child: Column(
                  children: [
                    Text(
                      weekdays[i],
                      style: TextStyle(fontSize: 9, color: palette.muted),
                    ),
                    const SizedBox(height: 2),
                    Container(
                      width: 24,
                      height: 24,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: _isSameDay(days[i], now)
                            ? palette.primary
                            : Colors.transparent,
                        shape: BoxShape.circle,
                      ),
                      child: Text(
                        '${days[i].day}',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: _isSameDay(days[i], now)
                              ? Colors.white
                              : palette.ink,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 2),
        if (_viewLoading)
          LinearProgressIndicator(
            color: palette.primary,
            backgroundColor: palette.primarySoft,
          ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: 20),
            child: SizedBox(
              height: 24 * hourHeight,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 38,
                    child: Column(
                      children: [
                        for (var hour = 0; hour < 24; hour++)
                          SizedBox(
                            height: hourHeight,
                            child: Align(
                              alignment: Alignment.topRight,
                              child: Padding(
                                padding: const EdgeInsets.only(right: 4),
                                child: Text(
                                  '${hour.toString().padLeft(2, '0')}:00',
                                  style: TextStyle(
                                    fontSize: 8,
                                    color: palette.muted,
                                  ),
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  for (var i = 0; i < 7; i++)
                    Expanded(
                      child: _buildWeekDay(
                        days[i],
                        palette,
                        hourHeight,
                        now,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildWeekDay(
    DateTime day,
    AppPalette palette,
    double hourHeight,
    DateTime now,
  ) {
    final dayStart = DateTime(day.year, day.month, day.day);
    final dayEnd = dayStart.add(const Duration(days: 1));
    final events = _weekEvents.where((event) {
      final start = eventStart(event);
      final end = eventEnd(event);
      if (start == null || end == null) return false;
      return end.isAfter(dayStart) && start.isBefore(dayEnd);
    }).toList();
    return Container(
      decoration: BoxDecoration(
        border: Border(
          left: BorderSide(color: palette.line.withValues(alpha: 0.7)),
          bottom: BorderSide(color: palette.line.withValues(alpha: 0.7)),
        ),
      ),
      child: Stack(
        children: [
          for (var hour = 0; hour < 24; hour++)
            Positioned(
              top: hour * hourHeight,
              left: 0,
              right: 0,
              child: Container(
                height: hourHeight,
                decoration: BoxDecoration(
                  border: Border(
                    top: BorderSide(
                      color: palette.line.withValues(alpha: 0.55),
                    ),
                  ),
                ),
              ),
            ),
          for (final event in events)
            _weekEvent(event, dayStart, dayEnd, palette, hourHeight),
          if (_isSameDay(day, now))
            Positioned(
              top: (now.hour + now.minute / 60) * hourHeight,
              left: 0,
              right: 0,
              child: Container(height: 1.5, color: palette.accent),
            ),
        ],
      ),
    );
  }

  Widget _weekEvent(
    Map<String, dynamic> event,
    DateTime dayStart,
    DateTime dayEnd,
    AppPalette palette,
    double hourHeight,
  ) {
    final start = eventStart(event);
    final end = eventEnd(event);
    if (start == null || end == null) return const SizedBox.shrink();
    final visibleStart = start.isBefore(dayStart) ? dayStart : start;
    final visibleEnd = end.isAfter(dayEnd) ? dayEnd : end;
    final top = (visibleStart.hour + visibleStart.minute / 60) * hourHeight;
    final height =
        ((visibleEnd.difference(visibleStart).inMinutes / 60) * hourHeight)
            .clamp(20.0, 24 * hourHeight);
    return Positioned(
      top: top,
      left: 1,
      right: 1,
      height: height,
      child: GestureDetector(
        onTap: () => _edit(event),
        child: Container(
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            color: palette.primary.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(
              color: palette.primary.withValues(alpha: 0.35),
            ),
          ),
          child: Text(
            (event['title'] ?? '').toString(),
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 8,
              height: 1.15,
              fontWeight: FontWeight.w600,
              color: palette.primary,
            ),
          ),
        ),
      ),
    );
  }

  bool _isSameDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }

  Widget _sectionTitle(String title, int count, AppPalette palette) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 4, 8),
      child: Row(
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 0.6,
              fontWeight: FontWeight.w800,
              color: palette.muted,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            '$count',
            style: TextStyle(fontSize: 10, color: palette.muted),
          ),
        ],
      ),
    );
  }

  Widget _eventCard(
    Map<String, dynamic> event, {
    required bool ended,
    required AppPalette palette,
  }) {
    final title = (event['title'] ?? '无标题').toString();
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: ended
              ? palette.line
              : Theme.of(context).colorScheme.primaryContainer,
          child: Icon(
            ended ? Icons.event_available_outlined : Icons.event,
            color:
                ended ? palette.muted : Theme.of(context).colorScheme.primary,
          ),
        ),
        title: Text(
          title,
          style: TextStyle(
            decoration: ended ? TextDecoration.lineThrough : null,
            color: ended ? palette.muted : palette.ink,
            fontWeight: ended ? FontWeight.w500 : FontWeight.w600,
          ),
        ),
        subtitle: Text(
          ended ? '${_fmtRange(event)} · 已结束' : _fmtRange(event),
          style: TextStyle(
            fontSize: 11,
            color: ended ? palette.muted : null,
          ),
        ),
        onTap: () => _edit(event),
        trailing: IconButton(
          icon: const Icon(Icons.delete_outline),
          onPressed: () async {
            final id = event['id'];
            if (id is int) {
              await ApiService().deleteScheduleEvent(id);
              _refreshCurrentView();
            }
          },
        ),
      ),
    );
  }

  int _compareByStart(Map<String, dynamic> a, Map<String, dynamic> b) {
    final left = eventStart(a);
    final right = eventStart(b);
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    return left.compareTo(right);
  }

  int _compareByEndDesc(Map<String, dynamic> a, Map<String, dynamic> b) {
    final left = eventEnd(a);
    final right = eventEnd(b);
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    return right.compareTo(left);
  }

  String _fmtRange(Map<String, dynamic> event) {
    final start = eventStart(event);
    if (start == null) return '';
    final end = eventEnd(event);
    final startText = '${start.month}/${start.day} ${_fmtClock(start)}';
    if (end == null) return startText;
    if (end.year == start.year &&
        end.month == start.month &&
        end.day == start.day) {
      return '$startText-${_fmtClock(end)}';
    }
    return '$startText - ${end.month}/${end.day} ${_fmtClock(end)}';
  }

  String _fmtClock(DateTime dt) {
    return '${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}
