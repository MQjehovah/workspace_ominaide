import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Bind the current account's own DingTalk via the CLI device flow.
class DingtalkBindScreen extends StatefulWidget {
  const DingtalkBindScreen({super.key});

  @override
  State<DingtalkBindScreen> createState() => _DingtalkBindScreenState();
}

class _DingtalkBindScreenState extends State<DingtalkBindScreen> {
  Map<String, dynamic> _status = const {};
  Map<String, dynamic>? _login;
  bool _loading = true;
  bool _starting = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final status = await ApiService().dingtalkStatus();
      if (!mounted) return;
      setState(() {
        _status = status;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('读取钉钉状态失败：$e')),
      );
    }
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      final data = await ApiService().startDingtalkLogin();
      if (!mounted) return;
      setState(() => _login = data);
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('启动钉钉登录失败：$e')),
      );
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  Future<void> _poll() async {
    try {
      final data = await ApiService().dingtalkLoginStatus();
      if (!mounted) return;
      setState(() => _login = data);
      if (data['status'] == 'authorized') {
        _timer?.cancel();
        await _load();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('钉钉绑定成功')),
        );
      } else if (data['status'] == 'failed') {
        _timer?.cancel();
      }
    } catch (_) {
      // keep polling
    }
  }

  Future<void> _logout() async {
    try {
      await ApiService().dingtalkLogout();
      if (!mounted) return;
      setState(() => _login = null);
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('解绑失败：$e')),
      );
    }
  }

  void _copy(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('已复制')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final authenticated = _status['authenticated'] == true;
    final pending = _login?['status'] == 'pending';
    final code = _login?['user_code']?.toString();
    final url = _login?['verification_url']?.toString();

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'DingTalk',
              title: '钉钉',
              subtitle: '绑定当前账号自己的钉钉',
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
                        Row(
                          children: [
                            Icon(
                              authenticated
                                  ? Icons.verified_rounded
                                  : Icons.link_off_rounded,
                              color: authenticated
                                  ? Colors.green
                                  : palette.muted,
                              size: 20,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              authenticated ? '已绑定' : '未绑定',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: palette.ink,
                              ),
                            ),
                          ],
                        ),
                        if (_loading) ...[
                          const SizedBox(height: 12),
                          const LinearProgressIndicator(minHeight: 2),
                        ],
                        if (_status['error'] != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            _status['error'].toString(),
                            style: TextStyle(fontSize: 12, color: palette.muted),
                          ),
                        ],
                        const SizedBox(height: 8),
                        Text(
                          _status['dingtalk_dir']?.toString() ?? '',
                          style: TextStyle(fontSize: 11, color: palette.muted),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (pending && code != null)
                    AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '在钉钉中输入授权码',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: palette.ink,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              SelectableText(
                                code,
                                style: TextStyle(
                                  fontSize: 26,
                                  letterSpacing: 4,
                                  fontWeight: FontWeight.w800,
                                  color: palette.ink,
                                ),
                              ),
                              IconButton(
                                onPressed: () => _copy(code),
                                icon: const Icon(Icons.copy_rounded, size: 18),
                              ),
                            ],
                          ),
                          if (url != null && url.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            InkWell(
                              onTap: () => _copy(url),
                              child: Text(
                                url,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: palette.accent,
                                ),
                              ),
                            ),
                          ],
                          const SizedBox(height: 10),
                          Text(
                            '等待授权，完成后会自动刷新。',
                            style: TextStyle(fontSize: 11, color: palette.muted),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _starting || pending ? null : _start,
                    icon: Icon(
                      pending ? Icons.hourglass_top_rounded : Icons.login_rounded,
                    ),
                    label: Text(pending
                        ? '等待钉钉授权'
                        : authenticated
                            ? '重新绑定钉钉'
                            : '绑定我的钉钉'),
                  ),
                  if (authenticated) ...[
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _logout,
                      icon: const Icon(Icons.link_off_rounded),
                      label: const Text('解绑钉钉'),
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
