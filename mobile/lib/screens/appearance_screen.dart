import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class AppearanceScreen extends StatefulWidget {
  const AppearanceScreen({super.key});

  @override
  State<AppearanceScreen> createState() => _AppearanceScreenState();
}

class _AppearanceScreenState extends State<AppearanceScreen> {
  late double _hue;
  late double _fontScale;
  bool _draggingHue = false;

  @override
  void initState() {
    super.initState();
    _hue = HSVColor.fromColor(appTheme.seed).hue;
    _fontScale = appTheme.fontScale;
  }

  Color get _previewSeed => _draggingHue
      ? HSVColor.fromAHSV(1, _hue, 0.78, 0.95).toColor()
      : appTheme.seed;

  String _hex(Color color) {
    final value = color.toARGB32().toRadixString(16).padLeft(8, '0');
    return '#${value.substring(2).toUpperCase()}';
  }

  Future<void> _pickPreset(Color color) async {
    await appTheme.setSeed(color);
    if (!mounted) return;
    setState(() => _hue = HSVColor.fromColor(color).hue);
    await ApiService().pushAppearanceSetting('primary', _hex(color));
  }

  Future<void> _commitHue(double value) async {
    final color = HSVColor.fromAHSV(1, value, 0.78, 0.95).toColor();
    if (!mounted) return;
    setState(() => _draggingHue = false);
    await appTheme.setSeed(color);
    await ApiService().pushAppearanceSetting('primary', _hex(color));
  }

  Future<void> _setMode(ThemeMode mode) async {
    await appTheme.setMode(mode);
    await ApiService().pushAppearanceSetting('mode', mode.name);
  }

  Future<void> _setTint(bool value) async {
    await appTheme.setTint(value);
    await ApiService().pushAppearanceSetting('tint', value);
  }

  Future<void> _commitFont(double value) async {
    await appTheme.setFontScale(value);
    await ApiService().pushAppearanceSetting('font_scale', value);
  }

  Future<void> _syncFromRemote() async {
    try {
      final settings = await ApiService().getAppearanceSettings();
      if (!mounted) return;
      if (settings.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('没有可同步的外观设置')),
        );
        return;
      }
      await appTheme.applyRemote(settings);
      if (!mounted) return;
      setState(() {
        _hue = HSVColor.fromColor(appTheme.seed).hue;
        _fontScale = appTheme.fontScale;
        _draggingHue = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已从其他设备同步外观设置')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('同步失败，请稍后重试')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final seed = _previewSeed;
    final soft = mixWithWhite(seed, 0.9);
    final light = mixWithWhite(seed, 0.32);

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Appearance',
              title: '外观与主题',
              subtitle: '设置会同步到 Web 和桌面',
              actions: [
                RoundIconButton(
                  icon: Icons.sync_rounded,
                  tooltip: '从其他设备同步',
                  onTap: _syncFromRemote,
                ),
                const SizedBox(width: 6),
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
                        Text(
                          '主题色',
                          style: TextStyle(
                            fontSize: 10,
                            letterSpacing: 1.1,
                            fontWeight: FontWeight.w700,
                            color: palette.muted,
                          ),
                        ),
                        const SizedBox(height: 9),
                        Row(
                          children: [
                            for (final preset in kThemePresets)
                              Padding(
                                padding: const EdgeInsets.only(right: 10),
                                child: _ColorDot(
                                  color: preset.color,
                                  selected: appTheme.seed.toARGB32() ==
                                      preset.color.toARGB32(),
                                  onTap: () => _pickPreset(preset.color),
                                ),
                              ),
                            _ColorDot(
                              color: seed,
                              selected: !kThemePresets.any(
                                (preset) =>
                                    preset.color.toARGB32() ==
                                    appTheme.seed.toARGB32(),
                              ),
                              custom: true,
                              onTap: () {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('拖动下方色相条即可自定义主题色'),
                                  ),
                                );
                              },
                            ),
                            const Spacer(),
                            Text(
                              _hex(seed),
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: palette.muted,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Stack(
                          alignment: Alignment.center,
                          children: [
                            Container(
                              height: 10,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(10),
                                gradient: LinearGradient(
                                  colors: [
                                    for (var i = 0; i <= 6; i++)
                                      HSVColor.fromAHSV(
                                        1,
                                        i * 60.0,
                                        0.78,
                                        0.95,
                                      ).toColor(),
                                  ],
                                ),
                              ),
                            ),
                            SliderTheme(
                              data: SliderTheme.of(context).copyWith(
                                trackHeight: 10,
                                activeTrackColor: Colors.transparent,
                                inactiveTrackColor: Colors.transparent,
                                thumbColor: Colors.white,
                                overlayColor: Colors.white24,
                                thumbShape: const RoundSliderThumbShape(
                                  enabledThumbRadius: 8,
                                ),
                                trackShape: const RoundedRectSliderTrackShape(),
                              ),
                              child: Slider(
                                value: _hue,
                                min: 0,
                                max: 360,
                                onChanged: (value) => setState(() {
                                  _hue = value;
                                  _draggingHue = true;
                                }),
                                onChangeEnd: _commitHue,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '预览',
                          style: TextStyle(
                            fontSize: 10,
                            letterSpacing: 1.1,
                            fontWeight: FontWeight.w700,
                            color: palette.muted,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: mixWithWhite(seed, 0.94),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 10,
                                  vertical: 7,
                                ),
                                decoration: BoxDecoration(
                                  color: seed,
                                  borderRadius: const BorderRadius.only(
                                    topLeft: Radius.circular(11),
                                    topRight: Radius.circular(11),
                                    bottomLeft: Radius.circular(11),
                                    bottomRight: Radius.circular(3),
                                  ),
                                ),
                                child: const Text(
                                  '帮我看看今天最重要的三件事',
                                  style: TextStyle(
                                    fontSize: 10.5,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 6),
                              Align(
                                alignment: Alignment.centerLeft,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 7,
                                  ),
                                  decoration: BoxDecoration(
                                    color: palette.card,
                                    borderRadius: const BorderRadius.only(
                                      topLeft: Radius.circular(11),
                                      topRight: Radius.circular(11),
                                      bottomLeft: Radius.circular(3),
                                      bottomRight: Radius.circular(11),
                                    ),
                                    border: Border.all(color: palette.line),
                                  ),
                                  child: Text(
                                    '先过预算评审，再回复客户；周报还差项目进展。',
                                    style: TextStyle(
                                      fontSize: 10.5,
                                      color: palette.ink,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 7),
                              Container(
                                width: 28,
                                height: 28,
                                decoration: BoxDecoration(
                                  color: seed,
                                  borderRadius: BorderRadius.circular(9),
                                ),
                                child: const Icon(
                                  Icons.send_rounded,
                                  size: 14,
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '模式',
                          style: TextStyle(
                            fontSize: 10,
                            letterSpacing: 1.1,
                            fontWeight: FontWeight.w700,
                            color: palette.muted,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _modeChip(palette, ThemeMode.system, '跟随系统'),
                            const SizedBox(width: 6),
                            _modeChip(palette, ThemeMode.light, '浅色'),
                            const SizedBox(width: 6),
                            _modeChip(palette, ThemeMode.dark, '深色'),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  AppCard(
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '背景跟随主题色',
                                style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                  color: palette.ink,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '只做很浅的染色，保持可读性',
                                style: TextStyle(
                                  fontSize: 10,
                                  color: palette.muted,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Switch(
                          value: appTheme.tintBackground,
                          thumbColor: WidgetStatePropertyAll(palette.primary),
                          onChanged: _setTint,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              '字体大小',
                              style: TextStyle(
                                fontSize: 12.5,
                                fontWeight: FontWeight.w700,
                                color: palette.ink,
                              ),
                            ),
                            const Spacer(),
                            Text(
                              _fontScale <= 0.95
                                  ? '小'
                                  : _fontScale >= 1.2
                                      ? '大'
                                      : '标准',
                              style: TextStyle(
                                fontSize: 10,
                                color: palette.muted,
                              ),
                            ),
                          ],
                        ),
                        Slider(
                          value: _fontScale,
                          min: 0.9,
                          max: 1.3,
                          divisions: 4,
                          activeColor: seed,
                          label: '${_fontScale.toStringAsFixed(1)}x',
                          onChanged: (value) =>
                              setState(() => _fontScale = value),
                          onChangeEnd: _commitFont,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '主题色会应用到发送按钮、用户气泡、链接和选中态。深色模式会自动降低饱和度。',
                    style: TextStyle(
                      fontSize: 10.5,
                      height: 1.6,
                      color: palette.muted,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Container(
                        width: 16,
                        height: 16,
                        decoration: BoxDecoration(
                          color: light,
                          borderRadius: BorderRadius.circular(5),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Container(
                        width: 16,
                        height: 16,
                        decoration: BoxDecoration(
                          color: soft,
                          borderRadius: BorderRadius.circular(5),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _modeChip(AppPalette palette, ThemeMode mode, String label) {
    final selected = appTheme.mode == mode;
    return Expanded(
      child: InkWell(
        onTap: () => _setMode(mode),
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected ? palette.primary : palette.background,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: selected ? palette.primary : palette.line,
            ),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: selected ? Colors.white : palette.muted,
            ),
          ),
        ),
      ),
    );
  }
}

class _ColorDot extends StatelessWidget {
  const _ColorDot({
    required this.color,
    required this.selected,
    required this.onTap,
    this.custom = false,
  });

  final Color color;
  final bool selected;
  final VoidCallback onTap;
  final bool custom;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      customBorder: const CircleBorder(),
      child: Container(
        width: 30,
        height: 30,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? Theme.of(context).colorScheme.onSurface : Colors.transparent,
            width: 2,
          ),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.25),
              blurRadius: 8,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: custom
            ? const Icon(Icons.add, size: 14, color: Colors.white)
            : null,
      ),
    );
  }
}
