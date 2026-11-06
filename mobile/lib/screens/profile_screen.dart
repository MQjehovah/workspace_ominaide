import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'appearance_screen.dart';
import 'brief_screen.dart';
import 'bots_screen.dart';
import 'device_screen.dart';
import 'login_screen.dart';
import 'mcp_screen.dart';
import 'memory_screen.dart';
import 'notifications_screen.dart';
import 'settings_screen.dart';
import 'vibecoding_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String _name = '';
  String _email = '';
  int _pendingMemories = 0;
  Map<String, dynamic>? _profile;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = ApiService();
    Map<String, dynamic>? me;
    Map<String, dynamic>? profile;
    List<Map<String, dynamic>> candidates = [];
    try {
      me = await api.getMe();
    } catch (_) {}
    try {
      profile = await api.getProfile();
    } catch (_) {}
    try {
      candidates = await api.listMemoryCandidates();
    } catch (_) {}
    if (!mounted) return;
    final profileName = (profile?['name'] ?? '').toString().trim();
    setState(() {
      _profile = profile;
      _name = profileName.isNotEmpty
          ? profileName
          : (me?['username'] ?? '').toString();
      _email = (me?['email'] ?? '').toString();
      _pendingMemories = candidates.length;
    });
  }

  Future<void> _editProfile() async {
    final name = TextEditingController(text: _name);
    final role = TextEditingController(
      text: (_profile?['role'] ?? '').toString(),
    );
    final company = TextEditingController(
      text: (_profile?['company'] ?? '').toString(),
    );
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) {
        final palette = AppPalette.of(context);
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '编辑资料',
            style: TextStyle(fontSize: 16, color: palette.ink),
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: '名字'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: role,
                  decoration: const InputDecoration(labelText: '职位'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: company,
                  decoration: const InputDecoration(labelText: '公司'),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
    if (saved == true) {
      try {
        await ApiService().updateProfile({
          'name': name.text.trim(),
          'role': role.text.trim(),
          'company': company.text.trim(),
        });
        if (!mounted) return;
        await _load();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('资料已更新')),
        );
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败：$e')),
        );
      }
    }
    name.dispose();
    role.dispose();
    company.dispose();
  }

  Future<void> _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('退出登录？'),
        content: const Text('本地主题设置会保留。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ApiService().logout();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  void _push(Widget page) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => page));
  }

  String get _themeLabel {
    for (final preset in kThemePresets) {
      if (preset.color.toARGB32() == appTheme.seed.toARGB32()) {
        return preset.name;
      }
    }
    return '自定义';
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final displayName = _name.isEmpty ? '未命名用户' : _name;
    final initial = displayName.substring(0, 1);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          color: palette.primary,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              PageHeader(
                kicker: 'Profile',
                title: '我的',
                subtitle: '账号、偏好与连接',
                actions: [
                  RoundIconButton(
                    icon: Icons.settings_outlined,
                    tooltip: '设置',
                    onTap: () => _push(const SettingsScreen()),
                  ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  children: [
                    AppCard(
                      padding: const EdgeInsets.all(13),
                      child: Row(
                        children: [
                          Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  palette.accent.withValues(alpha: 0.55),
                                  palette.accent,
                                ],
                              ),
                              borderRadius: BorderRadius.circular(17),
                            ),
                            alignment: Alignment.center,
                            child: Text(
                              initial,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                                color: Colors.white,
                              ),
                            ),
                          ),
                          const SizedBox(width: 11),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  displayName,
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w800,
                                    color: palette.ink,
                                  ),
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  _email.isEmpty ? '已登录' : _email,
                                  style: TextStyle(
                                    fontSize: 10.5,
                                    color: palette.muted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          InkWell(
                            onTap: _editProfile,
                            borderRadius: BorderRadius.circular(8),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 4,
                                vertical: 2,
                              ),
                              child: Text(
                                '编辑',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                  color: palette.primary,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    _Group(
                      title: '智能',
                      palette: palette,
                      children: [
                        _MenuRow(
                          icon: Icons.smart_toy_outlined,
                          color: palette.primary,
                          title: 'AI 角色',
                          value: '切换助理',
                          onTap: () => _push(const BotsScreen()),
                        ),
                        _MenuRow(
                          icon: Icons.auto_awesome_outlined,
                          color: palette.primary,
                          title: '记忆与关于我',
                          badge: _pendingMemories > 0
                              ? '$_pendingMemories 待审核'
                              : null,
                          onTap: () => _push(const MemoryScreen()),
                        ),
                        _MenuRow(
                          icon: Icons.auto_graph_outlined,
                          color: palette.accent,
                          title: '幕僚长偏好',
                          value: '简报 08:30',
                          onTap: () => _push(const BriefScreen()),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    _Group(
                      title: '外观',
                      palette: palette,
                      children: [
                        _MenuRow(
                          icon: Icons.palette_outlined,
                          color: const Color(0xFF7C5CF6),
                          title: '外观与主题',
                          value: _themeLabel,
                          onTap: () => _push(const AppearanceScreen()),
                        ),
                        _MenuRow(
                          icon: Icons.notifications_none_rounded,
                          color: palette.success,
                          title: '通知与提醒',
                          value: '已开启',
                          onTap: () => _push(const NotificationsScreen()),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    _Group(
                      title: '连接',
                      palette: palette,
                      children: [
                        _MenuRow(
                          icon: Icons.devices_other_outlined,
                          color: palette.success,
                          title: '设备',
                          value: '在线',
                          onTap: () => _push(const DeviceScreen()),
                        ),
                        _MenuRow(
                          icon: Icons.hub_outlined,
                          color: palette.primary,
                          title: 'MCP 与集成',
                          onTap: () => _push(const McpScreen()),
                        ),
                        _MenuRow(
                          icon: Icons.science_outlined,
                          color: palette.muted,
                          title: '实验室 · VibeCoding',
                          onTap: () => _push(const VibecodingScreen()),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    TextButton(
                      onPressed: _logout,
                      child: Text(
                        '退出登录',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: palette.accent,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Group extends StatelessWidget {
  const _Group({
    required this.title,
    required this.palette,
    required this.children,
  });

  final String title;
  final AppPalette palette;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(title: title, padding: const EdgeInsets.fromLTRB(2, 0, 2, 5)),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              for (var i = 0; i < children.length; i++) ...[
                children[i],
                if (i != children.length - 1)
                  Divider(height: 1, color: palette.line),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow({
    required this.icon,
    required this.color,
    required this.title,
    required this.onTap,
    this.value,
    this.badge,
  });

  final IconData icon;
  final Color color;
  final String title;
  final VoidCallback onTap;
  final String? value;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        child: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(9),
              ),
              child: Icon(icon, size: 15, color: color),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: palette.ink,
                ),
              ),
            ),
            if (badge != null)
              Container(
                margin: const EdgeInsets.only(right: 4),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: palette.accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  badge!,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w800,
                    color: palette.accent,
                  ),
                ),
              ),
            if (value != null)
              Text(
                value!,
                style: TextStyle(fontSize: 10, color: palette.muted),
              ),
            const SizedBox(width: 2),
            Icon(Icons.chevron_right_rounded, size: 16, color: palette.muted),
          ],
        ),
      ),
    );
  }
}
