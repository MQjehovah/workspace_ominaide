import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class McpScreen extends StatefulWidget {
  const McpScreen({super.key});

  @override
  State<McpScreen> createState() => _McpScreenState();
}

class _McpScreenState extends State<McpScreen> {
  List<Map<String, dynamic>> _servers = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    List<Map<String, dynamic>> servers = [];
    try {
      servers = await ApiService().listMcpServers();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _servers = servers;
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
              kicker: 'MCP',
              title: 'MCP 与集成',
              subtitle: '${_servers.length} 个服务器',
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
                      child: _servers.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: const [
                                SizedBox(height: 50),
                                EmptyState(
                                  icon: Icons.hub_outlined,
                                  title: '还没有连接 MCP',
                                  subtitle: '在 Web 的「MCP 管理」中添加钉钉、Home Assistant 等服务器。',
                                ),
                              ],
                            )
                          : ListView.builder(
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                              itemCount: _servers.length,
                              itemBuilder: (context, index) {
                                final server = _servers[index];
                                final enabled = server['enabled'] != false;
                                final status =
                                    (server['last_status'] ?? 'unknown').toString();
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: AppCard(
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 34,
                                          height: 34,
                                          decoration: BoxDecoration(
                                            color: palette.primarySoft,
                                            borderRadius: BorderRadius.circular(11),
                                          ),
                                          child: Icon(
                                            Icons.hub_outlined,
                                            size: 17,
                                            color: palette.primary,
                                          ),
                                        ),
                                        const SizedBox(width: 10),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                (server['name'] ?? 'MCP').toString(),
                                                style: TextStyle(
                                                  fontSize: 13,
                                                  fontWeight: FontWeight.w700,
                                                  color: palette.ink,
                                                ),
                                              ),
                                              const SizedBox(height: 2),
                                              Text(
                                                '${server['slug'] ?? ''} · ${server['tools_count'] ?? 0} 个工具',
                                                style: TextStyle(
                                                  fontSize: 10.5,
                                                  color: palette.muted,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        SourcePill(
                                          label: !enabled
                                              ? '已停用'
                                              : status == 'connected'
                                                  ? '已连接'
                                                  : status,
                                          color: !enabled
                                              ? palette.muted
                                              : status == 'connected'
                                                  ? palette.success
                                                  : palette.accent,
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
