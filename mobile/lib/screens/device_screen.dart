import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'vibecoding_screen.dart';

class DeviceScreen extends StatefulWidget {
  const DeviceScreen({super.key});

  @override
  State<DeviceScreen> createState() => _DeviceScreenState();
}

class _DeviceScreenState extends State<DeviceScreen> {
  List<dynamic> _devices = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final devices = await ApiService().listVibecodingDevices();
    if (!mounted) return;
    setState(() {
      _devices = devices;
      _loading = false;
    });
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
              kicker: 'Devices',
              title: '设备',
              subtitle: '${_devices.length} 个已连接',
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
                      child: _devices.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: const [
                                SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.devices_other_outlined,
                                  title: '还没有连接设备',
                                  subtitle: '在桌面端或设备上登录同一个账号后，会显示在这里。',
                                ),
                              ],
                            )
                          : ListView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              itemCount: _devices.length,
                              itemBuilder: (context, index) {
                                final raw = _devices[index];
                                final device = raw is Map
                                    ? raw.map((k, v) => MapEntry(k.toString(), v))
                                    : <String, dynamic>{};
                                final name = (device['name'] ??
                                        device['device_id'] ??
                                        '设备')
                                    .toString();
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: AppCard(
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 34,
                                          height: 34,
                                          decoration: BoxDecoration(
                                            color: palette.success
                                                .withValues(alpha: 0.12),
                                            borderRadius: BorderRadius.circular(11),
                                          ),
                                          child: Icon(
                                            Icons.devices_other_outlined,
                                            size: 17,
                                            color: palette.success,
                                          ),
                                        ),
                                        const SizedBox(width: 10),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                name,
                                                style: TextStyle(
                                                  fontSize: 13,
                                                  fontWeight: FontWeight.w700,
                                                  color: palette.ink,
                                                ),
                                              ),
                                              const SizedBox(height: 2),
                                              Text(
                                                (device['platform'] ??
                                                        device['device_id'] ??
                                                        '')
                                                    .toString(),
                                                style: TextStyle(
                                                  fontSize: 10.5,
                                                  color: palette.muted,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        SourcePill(
                                          label: (device['status'] ?? '在线')
                                              .toString(),
                                          color: palette.success,
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: OutlinedButton.icon(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const VibecodingScreen()),
                ),
                icon: const Icon(Icons.science_outlined, size: 17),
                label: const Text('打开实验室 · VibeCoding'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(42),
                  foregroundColor: palette.primary,
                  side: BorderSide(color: palette.line),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
