import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// SmartAssistant hardware device (ESP32): firmware, gestures and push.
class DeviceScreen extends StatefulWidget {
  const DeviceScreen({super.key});

  @override
  State<DeviceScreen> createState() => _DeviceScreenState();
}

class _DeviceScreenState extends State<DeviceScreen> {
  static const _gestureLabels = {
    'flip': '翻转',
    'shake': '摇一摇',
    'double_tap': '双击',
    'pickup': '拿起',
  };

  bool _loading = true;
  Map<String, dynamic> _firmware = {};
  Map<String, dynamic> _gestures = {};
  bool _haConfigured = false;
  bool _pushing = false;
  final _title = TextEditingController();
  final _body = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        ApiService().deviceFirmware(),
        ApiService().deviceGestures(),
      ]);
      final gestures = results[1];
      if (!mounted) return;
      setState(() {
        _firmware = results[0];
        _gestures = gestures['gestures'] is Map
            ? Map<String, dynamic>.from(gestures['gestures'] as Map)
            : {};
        _haConfigured = gestures['ha_configured'] == true;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _push() async {
    final title = _title.text.trim();
    if (title.isEmpty) {
      _toast('请填写标题');
      return;
    }
    setState(() => _pushing = true);
    try {
      await ApiService().pushToDevice(
        title: title,
        body: _body.text.trim(),
      );
      if (!mounted) return;
      _title.clear();
      _body.clear();
      _toast('已推送到设备');
    } catch (e) {
      if (mounted) {
        _toast('推送失败：${e.toString().replaceFirst('Exception: ', '')}');
      }
    } finally {
      if (mounted) setState(() => _pushing = false);
    }
  }

  void _toast(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
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
              kicker: 'Device',
              title: '设备',
              subtitle: 'SmartAssistant · ESP32',
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
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                        children: [
                          _buildFirmware(palette),
                          const SizedBox(height: 10),
                          _buildPush(palette),
                          const SizedBox(height: 10),
                          _buildGestures(palette),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFirmware(AppPalette palette) {
    final available = _firmware['available'] == true;
    final version = (_firmware['version'] ?? '').toString();
    final size = (_firmware['size'] as num?)?.toInt() ?? 0;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionTitle(palette, '固件更新'),
          const SizedBox(height: 8),
          Text(
            available
                ? '后端已发布 v$version（${(size / 1024).round()} KB）'
                : '后端尚未发布固件。',
            style: TextStyle(fontSize: 12.5, height: 1.6, color: palette.ink),
          ),
          const SizedBox(height: 6),
          Text(
            '设备设置页点两次「检查固件更新」即可升级。',
            style: TextStyle(fontSize: 11, color: palette.muted),
          ),
        ],
      ),
    );
  }

  Widget _buildPush(AppPalette palette) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionTitle(palette, '发送到设备'),
          const SizedBox(height: 8),
          TextField(
            controller: _title,
            decoration: const InputDecoration(
              labelText: '标题',
              hintText: '例如：该喝水了',
            ),
            maxLength: 120,
          ),
          const SizedBox(height: 6),
          TextField(
            controller: _body,
            decoration: const InputDecoration(
              labelText: '正文（可选）',
              hintText: '设备会在 1 秒内收到并提示',
            ),
            maxLines: 3,
            maxLength: 400,
          ),
          const SizedBox(height: 6),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _pushing ? null : _push,
              icon: _pushing
                  ? const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_rounded, size: 16),
              label: Text(_pushing ? '发送中…' : '推送到设备'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGestures(AppPalette palette) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _sectionTitle(palette, '手势 → 动作'),
              const Spacer(),
              SourcePill(
                label: _haConfigured ? 'HA 已配置' : 'HA 未配置',
                color: _haConfigured ? palette.success : palette.muted,
                icon: Icons.home_outlined,
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final entry in _gestureLabels.entries)
            _gestureRow(palette, entry.key, entry.value),
        ],
      ),
    );
  }

  Widget _gestureRow(AppPalette palette, String key, String fallbackLabel) {
    final item = _gestures[key];
    final map = item is Map ? item : const {};
    final label = (map['label'] ?? '').toString().trim();
    final tool = (map['tool'] ?? '').toString().trim();
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          SizedBox(
            width: 58,
            child: Text(
              fallbackLabel,
              style: TextStyle(fontSize: 12, color: palette.ink),
            ),
          ),
          Expanded(
            child: Text(
              label.isNotEmpty ? label : '未配置',
              style: TextStyle(
                fontSize: 11.5,
                color: label.isNotEmpty ? palette.ink : palette.muted,
              ),
            ),
          ),
          if (tool.isNotEmpty)
            Text(
              tool,
              style: TextStyle(fontSize: 10, color: palette.muted),
            ),
        ],
      ),
    );
  }

  Widget _sectionTitle(AppPalette palette, String text) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w800,
        letterSpacing: 0.4,
        color: palette.muted,
      ),
    );
  }
}
