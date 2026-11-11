import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'vibecoding_screen.dart';

class MachineScreen extends StatefulWidget {
  const MachineScreen({super.key});

  @override
  State<MachineScreen> createState() => _MachineScreenState();
}

class _MachineScreenState extends State<MachineScreen> {
  List<dynamic> _machines = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final machines = await ApiService().listVibecodingMachines();
    if (!mounted) return;
    setState(() {
      _machines = machines;
      _loading = false;
    });
  }

  Future<void> _rename(Map<String, dynamic> machine) async {
    final controller = TextEditingController(
      text: (machine['name'] ?? '').toString(),
    );
    final value = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('重命名本地机器'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: '名称',
            hintText: '留空恢复默认主机名',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (value == null) return;
    try {
      await ApiService().renameVibecodingMachine(
        (machine['machine_id'] ?? '').toString(),
        value,
      );
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('名称已更新')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content:
                Text('改名失败：${e.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _delete(Map<String, dynamic> machine) async {
    final online = machine['online'] == true || machine['status'] == 'online';
    if (online) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('该设备当前在线，请先在电脑上退出 OmniAide 登录后再删除'),
        ),
      );
      return;
    }
    final name = (machine['name'] ??
            machine['default_name'] ??
            machine['machine_id'] ??
            '本地机器')
        .toString();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除本地机器'),
        content: Text('确定要从列表中删除「$name」吗？\n设备下次登录后会重新出现。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ApiService().deleteVibecodingMachine(
        (machine['machine_id'] ?? '').toString(),
      );
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已删除')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '删除失败：${e.toString().replaceFirst('Exception: ', '')}',
          ),
        ),
      );
    }
  }

  int get _onlineCount => _machines.where((raw) {
        if (raw is! Map) return false;
        return raw['online'] == true || raw['status'] == 'online';
      }).length;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            PageHeader(
              kicker: 'Machines',
              title: '本地机器',
              subtitle: '${_machines.length} 台 · $_onlineCount 在线',
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
                  ? Center(
                      child: CircularProgressIndicator(color: palette.primary))
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: palette.primary,
                      child: _machines.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: const [
                                SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.computer_outlined,
                                  title: '还没有连接本地机器',
                                  subtitle: '在桌面端登录同一个账号后，会显示在这里。',
                                ),
                              ],
                            )
                          : ListView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              itemCount: _machines.length,
                              itemBuilder: (context, index) {
                                final raw = _machines[index];
                                final machine = raw is Map
                                    ? raw.map(
                                        (k, v) => MapEntry(k.toString(), v))
                                    : <String, dynamic>{};
                                final name = (machine['name'] ??
                                        machine['default_name'] ??
                                        machine['machine_id'] ??
                                        '本地机器')
                                    .toString();
                                final online = machine['online'] == true ||
                                    machine['status'] == 'online';
                                final platform =
                                    (machine['platform'] ?? 'desktop')
                                        .toString();
                                final lastSeen =
                                    (machine['last_seen'] ?? '').toString();
                                final seenShort = lastSeen.length > 16
                                    ? lastSeen.substring(0, 16)
                                    : lastSeen;
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
                                            borderRadius:
                                                BorderRadius.circular(11),
                                          ),
                                          child: Icon(
                                            Icons.computer_outlined,
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
                                                online
                                                    ? platform
                                                    : '$platform · 离线${seenShort.isNotEmpty ? ' $seenShort' : ''}',
                                                style: TextStyle(
                                                  fontSize: 10.5,
                                                  color: palette.muted,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        IconButton(
                                          onPressed: () => _rename(machine),
                                          icon: const Icon(Icons.edit_outlined,
                                              size: 16),
                                          tooltip: '重命名',
                                          visualDensity: VisualDensity.compact,
                                        ),
                                        IconButton(
                                          onPressed: () => _delete(machine),
                                          icon: Icon(
                                            Icons.delete_outline_rounded,
                                            size: 17,
                                            color: online
                                                ? palette.muted
                                                    .withValues(alpha: 0.4)
                                                : palette.accent,
                                          ),
                                          tooltip: online ? '在线设备不能删除' : '删除',
                                          visualDensity: VisualDensity.compact,
                                        ),
                                        SourcePill(
                                          label: online ? '在线' : '离线',
                                          color: online
                                              ? palette.success
                                              : palette.muted,
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
