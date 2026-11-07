import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/bot_selection_service.dart';
import '../services/file_transfer_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class MailComposeScreen extends StatefulWidget {
  const MailComposeScreen({
    super.key,
    this.replyTo,
    this.forwardOf,
    this.draftBody,
  });

  final Map<String, dynamic>? replyTo;
  final Map<String, dynamic>? forwardOf;
  final String? draftBody;

  @override
  State<MailComposeScreen> createState() => _MailComposeScreenState();
}

class _MailComposeScreenState extends State<MailComposeScreen> {
  final _to = TextEditingController();
  final _cc = TextEditingController();
  final _bcc = TextEditingController();
  final _subject = TextEditingController();
  final _body = TextEditingController();

  List<Map<String, dynamic>> _accounts = [];
  int? _accountId;
  final _attachments = <Map<String, dynamic>>[];
  bool _busy = false;
  bool _drafting = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    final source = widget.replyTo ?? widget.forwardOf;
    if (source != null) {
      final from = (source['from_address'] ?? '').toString();
      final subject = (source['subject'] ?? '').toString();
      if (widget.replyTo != null && from.isNotEmpty) {
        _to.text = from;
      }
      if (widget.forwardOf != null) {
        _subject.text = subject.startsWith('Fwd:') ? subject : 'Fwd: $subject';
      } else {
        _subject.text = subject.startsWith('Re:') ? subject : 'Re: $subject';
      }
      final content = (source['content'] ?? source['preview'] ?? '').toString();
      if (widget.forwardOf != null && content.isNotEmpty) {
        _body.text = '\n\n---------- 转发邮件 ----------\n$content';
      }
    }
    if (widget.draftBody != null && widget.draftBody!.trim().isNotEmpty) {
      _body.text = widget.draftBody!;
    }
    _loadAccounts();
  }

  @override
  void dispose() {
    _to.dispose();
    _cc.dispose();
    _bcc.dispose();
    _subject.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _loadAccounts() async {
    try {
      final accounts = await ApiService().listMailAccounts();
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _accountId = accounts.isNotEmpty
            ? (accounts.first['id'] as num?)?.toInt()
            : null;
      });
    } catch (_) {}
  }

  Future<void> _aiDraft() async {
    final source = widget.replyTo ?? widget.forwardOf;
    final id = (source?['id'] as num?)?.toInt();
    if (id == null || _drafting) return;
    setState(() => _drafting = true);
    try {
      final draft = await ApiService().getDraftReply(
        source: 'mail',
        messageId: id,
        botId: BotSelectionService().botId,
      );
      if (!mounted || draft == null) return;
      setState(() {
        final subject = (draft['subject'] ?? '').toString();
        final body = (draft['body'] ?? '').toString();
        if (subject.isNotEmpty) _subject.text = subject;
        if (body.isNotEmpty) _body.text = body;
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('生成草稿失败: $e')),
      );
    } finally {
      if (mounted) setState(() => _drafting = false);
    }
  }

  Future<void> _pickAttachments() async {
    final picked = await FilePicker.platform.pickFiles(allowMultiple: true);
    if (picked == null || picked.files.isEmpty || !mounted) return;
    setState(() => _busy = true);
    try {
      for (final file in picked.files) {
        final path = file.path;
        if (path == null) continue;
        final uploaded = await FileTransferService().upload(
          path,
          file.name,
          '/',
        );
        final id = (uploaded['id'] as num?)?.toInt();
        if (id == null) continue;
        setState(() {
          _attachments.add({
            'id': id,
            'name': file.name,
            'size': file.size,
          });
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('附件上传失败: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  List<String> _split(TextEditingController controller) {
    return controller.text
        .split(RegExp(r'[,;，；\s]+'))
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
  }

  Future<void> _send() async {
    if (_busy) return;
    final to = _split(_to);
    final subject = _subject.text.trim();
    if (to.isEmpty) {
      setState(() => _error = '请填写收件人');
      return;
    }
    if (subject.isEmpty) {
      setState(() => _error = '请填写主题');
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认发送？'),
        content: Text('收件人：${to.join(', ')}\n主题：$subject'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('发送'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await ApiService().sendMail(
        accountId: _accountId,
        to: to,
        cc: _split(_cc),
        bcc: _split(_bcc),
        subject: subject,
        body: _body.text,
        replyToId: (widget.replyTo?['id'] as num?)?.toInt(),
        attachmentFileIds: _attachments
            .map((e) => (e['id'] as num?)?.toInt())
            .whereType<int>()
            .toList(),
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('邮件已发送')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final replying = widget.replyTo != null;
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: replying ? 'Reply' : 'Compose',
              title: replying ? '回复邮件' : '写邮件',
              subtitle: '发送后自动保存到已发送',
              actions: [
                RoundIconButton(
                  icon: Icons.close_rounded,
                  onTap: () => Navigator.maybePop(context),
                ),
                const SizedBox(width: 6),
                if (replying)
                  RoundIconButton(
                    icon: Icons.auto_awesome,
                    tooltip: 'AI 起草',
                    onTap: _drafting ? null : _aiDraft,
                  ),
                if (replying) const SizedBox(width: 6),
                RoundIconButton(
                  icon: _busy ? Icons.hourglass_top : Icons.send_rounded,
                  tooltip: '发送',
                  onTap: _busy ? null : _send,
                ),
              ],
            ),
            if (_busy)
              LinearProgressIndicator(
                color: palette.primary,
                backgroundColor: palette.primarySoft,
              ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                children: [
                  if (_accounts.length > 1) ...[
                    DropdownButtonFormField<int>(
                      value: _accountId,
                      decoration: const InputDecoration(labelText: '发件账号'),
                      items: [
                        for (final account in _accounts)
                          DropdownMenuItem(
                            value: (account['id'] as num?)?.toInt(),
                            child: Text(
                              (account['email'] ?? account['name'] ?? '')
                                  .toString(),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (value) => setState(() => _accountId = value),
                    ),
                    const SizedBox(height: 10),
                  ],
                  TextField(
                    controller: _to,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: '收件人',
                      hintText: '多个地址用逗号分隔',
                      prefixIcon: Icon(Icons.person_outline, size: 18),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _cc,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: '抄送',
                      prefixIcon: Icon(Icons.group_outlined, size: 18),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _bcc,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: '密送',
                      prefixIcon: Icon(Icons.visibility_off_outlined, size: 18),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _subject,
                    decoration: const InputDecoration(
                      labelText: '主题',
                      prefixIcon: Icon(Icons.subject_rounded, size: 18),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _body,
                    minLines: 10,
                    maxLines: 24,
                    decoration: const InputDecoration(
                      hintText: '写点什么…',
                      alignLabelWithHint: true,
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (_attachments.isNotEmpty) ...[
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final item in _attachments)
                          InputChip(
                            avatar: const Icon(
                              Icons.attach_file_rounded,
                              size: 15,
                            ),
                            label: Text(
                              (item['name'] ?? '').toString(),
                              overflow: TextOverflow.ellipsis,
                            ),
                            onDeleted: () =>
                                setState(() => _attachments.remove(item)),
                          ),
                      ],
                    ),
                    const SizedBox(height: 8),
                  ],
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      onPressed: _busy ? null : _pickAttachments,
                      icon: const Icon(Icons.attach_file_rounded, size: 17),
                      label: const Text('添加附件'),
                    ),
                  ),
                  if (_error.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Text(
                      _error,
                      style: TextStyle(fontSize: 11.5, color: palette.accent),
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
