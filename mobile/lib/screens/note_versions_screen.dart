import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Version history for a note, with preview and restore.
class NoteVersionsScreen extends StatefulWidget {
  const NoteVersionsScreen({
    super.key,
    required this.noteId,
    required this.noteTitle,
  });

  final int noteId;
  final String noteTitle;

  @override
  State<NoteVersionsScreen> createState() => _NoteVersionsScreenState();
}

class _NoteVersionsScreenState extends State<NoteVersionsScreen> {
  List<Map<String, dynamic>> _versions = [];
  bool _loading = true;
  String? _error;
  bool _changed = false;

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
      final versions = await ApiService().noteVersions(widget.noteId);
      if (!mounted) return;
      setState(() {
        _versions = versions;
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

  Future<void> _preview(Map<String, dynamic> version) async {
    final versionId = (version['id'] as num?)?.toInt();
    if (versionId == null) return;
    try {
      final data = await ApiService().noteVersion(widget.noteId, versionId);
      if (!mounted) return;
      final markdown = ApiService().parseNoteMarkdown((data['content'] ?? '').toString());
      final palette = AppPalette.of(context);
      final restore = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text('版本 ${version['version'] ?? ''}'.trim()),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: markdown.trim().isEmpty
                  ? Text('（空内容）', style: TextStyle(color: palette.muted))
                  : MarkdownBody(
                      data: markdown,
                      selectable: true,
                      styleSheet: MarkdownStyleSheet(
                        p: TextStyle(fontSize: 12.5, height: 1.65, color: palette.ink),
                      ),
                    ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('关闭'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('恢复此版本'),
            ),
          ],
        ),
      );
      if (restore != true) return;
      await ApiService().restoreNoteVersion(widget.noteId, versionId);
      _changed = true;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已恢复该版本')),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('恢复失败: ${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  String _fmtTime(dynamic raw) {
    final d = DateTime.tryParse((raw ?? '').toString());
    if (d == null) return (raw ?? '').toString();
    final local = d.toLocal();
    return '${local.year}/${local.month}/${local.day} '
        '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: Scaffold(
        backgroundColor: palette.background,
        body: SafeArea(
          child: Column(
            children: [
              PageHeader(
                kicker: 'History',
                title: '版本历史',
                subtitle: widget.noteTitle,
                actions: [
                  RoundIconButton(
                    icon: Icons.arrow_back_rounded,
                    onTap: () => Navigator.pop(context, _changed),
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
                        : _versions.isEmpty
                            ? ListView(
                                physics: const AlwaysScrollableScrollPhysics(),
                                children: const [
                                  SizedBox(height: 50),
                                  EmptyState(
                                    icon: Icons.history,
                                    title: '还没有历史版本',
                                    subtitle: '每次保存后会自动生成一个版本。',
                                  ),
                                ],
                              )
                            : RefreshIndicator(
                                onRefresh: _load,
                                color: palette.primary,
                                child: ListView.separated(
                                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                                  itemCount: _versions.length,
                                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                                  itemBuilder: (context, index) {
                                    final v = _versions[index];
                                    return AppCard(
                                      onTap: () => _preview(v),
                                      child: Row(
                                        children: [
                                          Container(
                                            width: 34,
                                            height: 34,
                                            alignment: Alignment.center,
                                            decoration: BoxDecoration(
                                              color: palette.primarySoft,
                                              borderRadius: BorderRadius.circular(9),
                                            ),
                                            child: Text(
                                              'v${v['version'] ?? ''}',
                                              style: TextStyle(
                                                fontSize: 10,
                                                fontWeight: FontWeight.w800,
                                                color: palette.primary,
                                              ),
                                            ),
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  (v['title'] ?? widget.noteTitle).toString(),
                                                  maxLines: 1,
                                                  overflow: TextOverflow.ellipsis,
                                                  style: TextStyle(
                                                    fontSize: 12.5,
                                                    fontWeight: FontWeight.w700,
                                                    color: palette.ink,
                                                  ),
                                                ),
                                                const SizedBox(height: 2),
                                                Text(
                                                  _fmtTime(v['created_at']),
                                                  style: TextStyle(
                                                    fontSize: 10,
                                                    color: palette.muted,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          Icon(Icons.chevron_right, size: 16, color: palette.muted),
                                        ],
                                      ),
                                    );
                                  },
                                ),
                              ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
