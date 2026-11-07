import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Ask questions against the note knowledge base (RAG) with cited sources.
class NotesAskScreen extends StatefulWidget {
  const NotesAskScreen({
    super.key,
    required this.onOpenNote,
  });

  /// Opens a cited note in the editor. Provided by NotesScreen to avoid a
  /// circular dependency with the editor screen.
  final void Function(int noteId, String title) onOpenNote;

  @override
  State<NotesAskScreen> createState() => _NotesAskScreenState();
}

class _NotesAskScreenState extends State<NotesAskScreen> {
  final _question = TextEditingController();
  String _answer = '';
  List<Map<String, dynamic>> _sources = [];
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _question.dispose();
    super.dispose();
  }

  Future<void> _ask() async {
    final question = _question.text.trim();
    if (question.isEmpty || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _answer = '';
      _sources = [];
    });
    try {
      final data = await ApiService().askNotes(question);
      if (!mounted) return;
      setState(() {
        _answer = (data['answer'] ?? '').toString();
        _sources = ((data['sources'] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => e.map((k, v) => MapEntry(k.toString(), v)))
            .toList();
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

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Knowledge',
              title: '问笔记',
              subtitle: '基于你的笔记回答，并给出引用来源',
              actions: [
                RoundIconButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
              ],
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: [
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        TextField(
                          controller: _question,
                          minLines: 2,
                          maxLines: 5,
                          textInputAction: TextInputAction.newline,
                          decoration: const InputDecoration(
                            hintText: '例如：我最近的项目进展如何？',
                            border: InputBorder.none,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                '回答只基于笔记内容，没有依据时会明确说明。',
                                style: TextStyle(fontSize: 10.5, color: palette.muted),
                              ),
                            ),
                            const SizedBox(width: 8),
                            FilledButton.icon(
                              onPressed: _loading ? null : _ask,
                              icon: _loading
                                  ? const SizedBox(
                                      width: 14,
                                      height: 14,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : const Icon(Icons.auto_awesome, size: 16),
                              label: const Text('提问'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final prompt in const [
                        '总结我最近的笔记',
                        '我的项目有哪些进展？',
                        '帮我找出关于会议的记录',
                      ])
                        ActionChip(
                          label: Text(prompt, style: const TextStyle(fontSize: 11)),
                          onPressed: _loading
                              ? null
                              : () {
                                  _question.text = prompt;
                                  _ask();
                                },
                        ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  if (_error != null)
                    AppCard(
                      borderColor: palette.accent.withValues(alpha: 0.4),
                      child: Text(
                        _error!,
                        style: TextStyle(fontSize: 12, color: palette.accent),
                      ),
                    ),
                  if (_answer.isNotEmpty)
                    AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.auto_awesome, size: 15, color: palette.primary),
                              const SizedBox(width: 6),
                              Text(
                                '回答',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
                                  color: palette.primary,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          MarkdownBody(
                            data: _answer,
                            selectable: true,
                            styleSheet: MarkdownStyleSheet(
                              p: TextStyle(
                                fontSize: 13,
                                height: 1.7,
                                color: palette.ink,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (_sources.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text(
                      '引用来源',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        color: palette.ink,
                      ),
                    ),
                    const SizedBox(height: 6),
                    for (final source in _sources)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: AppCard(
                          onTap: () {
                            final id = (source['note_id'] as num?)?.toInt();
                            if (id == null) return;
                            widget.onOpenNote(
                              id,
                              (source['title'] ?? '笔记').toString(),
                            );
                          },
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Container(
                                width: 22,
                                height: 22,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: palette.primarySoft,
                                  borderRadius: BorderRadius.circular(7),
                                ),
                                child: Text(
                                  (source['index'] ?? 0).toString(),
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w800,
                                    color: palette.primary,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      (source['title'] ?? '未命名笔记').toString(),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w700,
                                        color: palette.ink,
                                      ),
                                    ),
                                    if ((source['snippet'] ?? '').toString().isNotEmpty) ...[
                                      const SizedBox(height: 3),
                                      Text(
                                        source['snippet'].toString(),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          fontSize: 10.5,
                                          height: 1.45,
                                          color: palette.muted,
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                              Icon(Icons.chevron_right, size: 16, color: palette.muted),
                            ],
                          ),
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
