import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Full MOSS transcript for a meeting. The minutes page only shows the
/// summary, so this keeps the original diarized text one tap away.
class MeetingTranscriptScreen extends StatefulWidget {
  const MeetingTranscriptScreen({
    super.key,
    required this.title,
    this.transcript = '',
    this.segments = const [],
  });

  final String title;
  final String transcript;
  final List<dynamic> segments;

  @override
  State<MeetingTranscriptScreen> createState() =>
      _MeetingTranscriptScreenState();
}

class _MeetingTranscriptScreenState extends State<MeetingTranscriptScreen> {
  final TextEditingController _search = TextEditingController();

  List<Map<String, dynamic>> get _segments => widget.segments
      .whereType<Map>()
      .map((row) => Map<String, dynamic>.from(row))
      .where((row) => (row['text'] ?? '').toString().trim().isNotEmpty)
      .toList();

  String get _fullText {
    if (widget.transcript.trim().isNotEmpty) return widget.transcript;
    return _segments.map(_segmentLine).join('\n');
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  String _clock(dynamic raw) {
    final seconds = raw is num ? raw.toInt() : int.tryParse('$raw') ?? 0;
    final safe = seconds < 0 ? 0 : seconds;
    final h = safe ~/ 3600;
    final m = (safe % 3600) ~/ 60;
    final s = safe % 60;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:'
          '${m.toString().padLeft(2, '0')}:'
          '${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  String _speaker(Map<String, dynamic> row) {
    final value = (row['speaker'] ?? row['speaker_id'] ?? '').toString();
    return value.isEmpty ? '发言人' : '说话人 $value';
  }

  String _segmentLine(Map<String, dynamic> row) {
    final stamp = _clock(row['start'] ?? row['start_time']);
    final speaker = _speaker(row);
    return '[$stamp] $speaker：${(row['text'] ?? '').toString()}';
  }

  List<Map<String, dynamic>> get _filtered {
    final query = _search.text.trim().toLowerCase();
    if (query.isEmpty) return _segments;
    return _segments.where((row) {
      return (row['text'] ?? '').toString().toLowerCase().contains(query) ||
          _speaker(row).toLowerCase().contains(query);
    }).toList();
  }

  Future<void> _copyAll() async {
    await Clipboard.setData(ClipboardData(text: _fullText));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('原文已复制')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final segments = _filtered;
    final charCount = _fullText.replaceAll(RegExp(r'\s+'), '').length;
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Transcript',
              title: '原文转写',
              subtitle:
                  '${_segments.length} 段 · 约 $charCount 字 · ${widget.title}',
              actions: [
                RoundIconButton(
                  icon: Icons.copy_rounded,
                  onTap: _fullText.isEmpty ? null : _copyAll,
                ),
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  hintText: '搜索原文 / 说话人',
                  prefixIcon: const Icon(Icons.search_rounded, size: 18),
                  isDense: true,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            Expanded(
              child: segments.isEmpty
                  ? _buildEmpty(palette)
                  : ListView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                      itemCount: segments.length,
                      itemBuilder: (context, index) {
                        final row = segments[index];
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: AppCard(
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Column(
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 6,
                                        vertical: 3,
                                      ),
                                      decoration: BoxDecoration(
                                        color: palette.primarySoft,
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        _clock(row['start']),
                                        style: TextStyle(
                                          fontSize: 9.5,
                                          fontFeatures: const [
                                            FontFeature.tabularFigures(),
                                          ],
                                          color: palette.primary,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      _speaker(row),
                                      style: TextStyle(
                                        fontSize: 9,
                                        color: palette.muted,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: SelectableText(
                                    (row['text'] ?? '').toString(),
                                    style: TextStyle(
                                      fontSize: 12.5,
                                      height: 1.65,
                                      color: palette.ink,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty(AppPalette palette) {
    if (_segments.isEmpty && _fullText.trim().isNotEmpty) {
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        child: AppCard(
          child: SelectableText(
            _fullText,
            style: TextStyle(fontSize: 12.5, height: 1.7, color: palette.ink),
          ),
        ),
      );
    }
    return Center(
      child: Text(
        _search.text.trim().isEmpty ? '这次转写没有原文' : '没有匹配的原文',
        style: TextStyle(fontSize: 12, color: palette.muted),
      ),
    );
  }
}
