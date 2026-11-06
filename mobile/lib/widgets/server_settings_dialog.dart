import 'package:flutter/material.dart';

import '../config.dart';
import '../services/api_service.dart';

/// Shared server-address editor. Used by the login screen (gear button) and by
/// Settings, so the address is never shown next to the username/password form.
Future<String?> showServerSettingsDialog(BuildContext context) async {
  final controller = TextEditingController(text: ApiService().baseUrl);
  final result = await showDialog<String>(
    context: context,
    builder: (ctx) {
      final scheme = Theme.of(ctx).colorScheme;
      return AlertDialog(
        title: const Text('服务器地址'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: controller,
              keyboardType: TextInputType.url,
              autocorrect: false,
              enableSuggestions: false,
              decoration: const InputDecoration(
                labelText: '服务器地址',
                hintText: kDefaultServerUrl,
                prefixIcon: Icon(Icons.dns_outlined),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              '默认：$kDefaultServerUrl',
              style: TextStyle(fontSize: 11, color: scheme.outline),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => controller.text = kDefaultServerUrl,
            child: const Text('恢复默认'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              final value = normalizeServerUrl(controller.text);
              Navigator.pop(ctx, value.isEmpty ? kDefaultServerUrl : value);
            },
            child: const Text('保存'),
          ),
        ],
      );
    },
  );
  controller.dispose();
  if (result == null) return null;
  await ApiService().setServerUrl(result);
  return ApiService().baseUrl;
}
