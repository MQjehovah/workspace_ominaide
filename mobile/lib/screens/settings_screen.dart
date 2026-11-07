import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/app_lock_service.dart';
import '../services/music_cache.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import '../widgets/server_settings_dialog.dart';
import 'dingtalk_bind_screen.dart';
import 'login_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _serverUrl = '';
  int _cacheBytes = 0;
  bool _appLock = false;
  String _dingtalkLabel = '检查中';

  @override
  void initState() {
    super.initState();
    _serverUrl = ApiService().baseUrl;
    _loadCacheSize();
    _loadAppLock();
    _loadDingtalk();
  }

  Future<void> _loadDingtalk() async {
    try {
      final status = await ApiService().dingtalkStatus();
      if (!mounted) return;
      setState(() => _dingtalkLabel =
          status['authenticated'] == true ? '已绑定' : '未绑定');
    } catch (_) {
      if (mounted) setState(() => _dingtalkLabel = '读取失败');
    }
  }

  Future<void> _openDingtalk() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const DingtalkBindScreen()),
    );
    await _loadDingtalk();
  }

  Future<void> _loadAppLock() async {
    final enabled = await AppLockService().isEnabled();
    if (mounted) setState(() => _appLock = enabled);
  }

  Future<void> _toggleAppLock(bool value) async {
    final ok = await AppLockService().authenticate();
    if (!ok) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('需要先通过 Face ID 或设备密码验证')),
      );
      return;
    }
    await AppLockService().setEnabled(value);
    if (mounted) setState(() => _appLock = value);
  }

  Future<void> _loadCacheSize() async {
    final bytes = await MusicCache().size();
    if (mounted) setState(() => _cacheBytes = bytes);
  }

  Future<void> _clearCache() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清理音乐缓存'),
        content: Text(
          '将删除已缓存的音乐（${_fmtBytes(_cacheBytes)}），下次播放时需要重新下载。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('清理'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await MusicCache().clear();
    await _loadCacheSize();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('音乐缓存已清理')),
    );
  }

  Future<void> _editServer() async {
    final previous = _serverUrl;
    final updated = await showServerSettingsDialog(context);
    if (!mounted || updated == null) return;
    setState(() => _serverUrl = updated);
    if (updated == previous) return;
    final relogin = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('服务器已更新'),
        content: const Text('服务器地址已保存，需要重新登录才能使用新的服务器。现在重新登录吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('稍后'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('重新登录'),
          ),
        ],
      ),
    );
    if (relogin == true) await _logout();
  }

  Future<void> _logout() async {
    await ApiService().logout();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
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
              kicker: 'Settings',
              title: '设置',
              subtitle: '账号与服务器',
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
                      children: [
                        _row(palette, '服务器', _serverUrl, onTap: _editServer),
                        Divider(height: 18, color: palette.line),
                        _row(palette, '钉钉', _dingtalkLabel,
                            onTap: _openDingtalk),
                        Divider(height: 18, color: palette.line),
                        _row(palette, '音乐缓存', _fmtBytes(_cacheBytes),
                            onTap: _clearCache,
                            trailingIcon: Icons.delete_outline),
                        Divider(height: 18, color: palette.line),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                          value: _appLock,
                          onChanged: _toggleAppLock,
                          title: Text(
                            '应用锁',
                            style: TextStyle(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: palette.ink,
                            ),
                          ),
                          subtitle: Text(
                            '打开或切回前台时使用 Face ID / 设备密码',
                            style: TextStyle(fontSize: 10.5, color: palette.muted),
                          ),
                        ),
                        Divider(height: 18, color: palette.line),
                        _row(palette, '版本', '1.0.0'),
                        Divider(height: 18, color: palette.line),
                        _row(palette, '产品', 'OmniAide'),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  AppCard(
                    child: Text(
                      'OmniAide 把对话、收件箱、日程、待办、文件和记忆放在一个工作空间里。'
                      '主题与外观设置会保存在本地，并 best-effort 同步到其他端。',
                      style: TextStyle(
                        fontSize: 11.5,
                        height: 1.7,
                        color: palette.muted,
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  OutlinedButton(
                    onPressed: _logout,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: palette.accent,
                      side: BorderSide(color: palette.accent.withValues(alpha: 0.4)),
                      minimumSize: const Size.fromHeight(44),
                    ),
                    child: const Text('退出登录'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _fmtBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  }

  Widget _row(AppPalette palette, String label, String value,
      {VoidCallback? onTap, IconData trailingIcon = Icons.edit_outlined}) {
    final row = Row(
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
            color: palette.ink,
          ),
        ),
        const Spacer(),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.right,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 11, color: palette.muted),
          ),
        ),
        if (onTap != null) ...[
          const SizedBox(width: 6),
          Icon(trailingIcon, size: 14, color: palette.muted),
        ],
      ],
    );
    if (onTap == null) return row;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: row,
      ),
    );
  }
}
