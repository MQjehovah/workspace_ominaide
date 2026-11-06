import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../widgets/server_settings_dialog.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;

  Future<void> _login() async {
    setState(() => _loading = true);
    try {
      await ApiService().login(ApiService().baseUrl, _username.text, _password.text);
      if (!mounted) return;
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeScreen()));
    } catch (e) {
      if (!mounted) return;
      final message = e.toString().replaceFirst('Exception: ', '');
      final looksLikeNetwork =
          message.contains('SocketException') || message.contains('ClientException');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(looksLikeNetwork ? '无法连接服务器，请检查网络或服务器地址' : message),
          action: looksLikeNetwork
              ? SnackBarAction(
                  label: '服务器设置',
                  onPressed: () => _openServerSettings(),
                )
              : null,
        ),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openServerSettings() async {
    final updated = await showServerSettingsDialog(context);
    if (!mounted || updated == null) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('服务器地址已更新')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Stack(
        children: [
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(color: scheme.primaryContainer, shape: BoxShape.circle),
                    child: Icon(Icons.auto_awesome, size: 36, color: scheme.primary),
                  ),
                  const SizedBox(height: 16),
                  const Text('OmniAide', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 6),
                  Text('登录你的工作空间', style: TextStyle(color: scheme.outline)),
                  const SizedBox(height: 36),
                  TextField(controller: _username, decoration: const InputDecoration(labelText: '用户名', prefixIcon: Icon(Icons.person_outline))),
                  const SizedBox(height: 14),
                  TextField(controller: _password, obscureText: true,
                    decoration: const InputDecoration(labelText: '密码', prefixIcon: Icon(Icons.lock_outline)),
                    onSubmitted: (_) => _login(),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 50,
                    child: FilledButton(
                      onPressed: _loading ? null : _login,
                      style: FilledButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                      child: _loading
                        ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('登录', style: TextStyle(fontSize: 16)),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // Discreet entry point for changing the server before signing in.
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: Padding(
                padding: const EdgeInsets.all(6),
                child: IconButton(
                  tooltip: '服务器设置',
                  onPressed: _openServerSettings,
                  icon: Icon(Icons.settings_outlined, size: 20, color: scheme.outline),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
