import 'package:flutter/material.dart';

import '../models/opencode_models.dart';
import '../theme/app_theme.dart';

/// Renders an OpenCode `ask_user` form (select / multiselect / text / number /
/// boolean). Returns the answer map through `Navigator.pop`.
class OpenCodeFormSheet extends StatefulWidget {
  const OpenCodeFormSheet({super.key, required this.form});

  final OpenCodeForm form;

  @override
  State<OpenCodeFormSheet> createState() => _OpenCodeFormSheetState();
}

class _OpenCodeFormSheetState extends State<OpenCodeFormSheet> {
  final Map<String, TextEditingController> _text = {};
  final Map<String, TextEditingController> _custom = {};
  final Map<String, dynamic> _values = {};
  final Map<String, List<String>> _selected = {};
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final field in widget.form.fields) {
      final key = _keyOf(field);
      if (key.isEmpty) continue;
      final type = (field['type'] ?? 'string').toString();
      final defaultValue = field['default'];
      if (type == 'multiselect') {
        _selected[key] = ((defaultValue as List?) ?? const [])
            .map((value) => value.toString())
            .toList();
      } else if (type == 'boolean') {
        _values[key] = defaultValue is bool ? defaultValue : false;
      } else if (type == 'number' || type == 'integer') {
        _text[key] = TextEditingController(
          text: defaultValue == null ? '' : defaultValue.toString(),
        );
      } else {
        _text[key] = TextEditingController(
          text: defaultValue == null ? '' : defaultValue.toString(),
        );
        final hasOptions =
            field['options'] is List && (field['options'] as List).isNotEmpty;
        if (hasOptions) {
          _values[key] = defaultValue?.toString() ?? '';
        }
      }
      if (field['custom'] == true) {
        _custom[key] = TextEditingController();
      }
    }
  }

  @override
  void dispose() {
    for (final controller in _text.values) {
      controller.dispose();
    }
    for (final controller in _custom.values) {
      controller.dispose();
    }
    super.dispose();
  }

  String _keyOf(Map<String, dynamic> field) => (field['key'] ?? '').toString();

  bool _visible(Map<String, dynamic> field) {
    final when = field['when'];
    if (when is! List || when.isEmpty) return true;
    for (final raw in when.whereType<Map>()) {
      final key = (raw['key'] ?? '').toString();
      final op = (raw['op'] ?? 'eq').toString();
      final expected = raw['value'];
      final actual = _values[key] ?? _selected[key];
      final equal = '$actual' == '$expected';
      if (op == 'neq' ? equal : !equal) return false;
    }
    return true;
  }

  void _submit() {
    final answer = <String, dynamic>{};
    for (final field in widget.form.fields) {
      if (!_visible(field) || field['hidden'] == true) continue;
      final key = _keyOf(field);
      if (key.isEmpty) continue;
      final type = (field['type'] ?? 'string').toString();
      final required = field['required'] == true;
      dynamic value;

      if (type == 'multiselect') {
        final chosen = _selected[key] ?? const <String>[];
        if (chosen.isNotEmpty) value = List<String>.from(chosen);
      } else if (type == 'boolean') {
        value = _values[key] == true;
      } else if (type == 'number' || type == 'integer') {
        final text = _text[key]?.text.trim() ?? '';
        if (text.isNotEmpty) {
          value = type == 'integer' ? int.tryParse(text) : num.tryParse(text);
        }
      } else if (type == 'external') {
        continue;
      } else {
        final custom = _custom[key]?.text.trim() ?? '';
        final text = _text[key]?.text.trim() ?? '';
        final hasOptions =
            field['options'] is List && (field['options'] as List).isNotEmpty;
        final chosen = (_values[key] ?? '').toString();
        value = custom.isNotEmpty
            ? custom
            : hasOptions
                ? chosen
                : text;
      }

      final empty = value == null ||
          (value is String && value.trim().isEmpty) ||
          (value is List && value.isEmpty);
      if (required && empty) {
        setState(() {
          _error = '请填写「${(field['title'] ?? field['key'] ?? '选项')}」';
        });
        return;
      }
      if (!empty) answer[key] = value;
    }
    if (answer.isEmpty && widget.form.fields.isNotEmpty) {
      setState(() => _error = '请先做出选择');
      return;
    }
    setState(() => _error = null);
    Navigator.of(context).pop(answer);
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final fields = widget.form.fields
        .where((field) => _visible(field) && field['hidden'] != true)
        .toList();

    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          0,
          20,
          MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.78,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.help_outline_rounded,
                      size: 19,
                      color: palette.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        widget.form.title,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: palette.ink,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '桌面端的 OpenCode 正在等待你的选择。',
                  style: TextStyle(fontSize: 11.5, color: palette.muted),
                ),
                const SizedBox(height: 14),
                for (final field in fields) ...[
                  _buildField(palette, field),
                  const SizedBox(height: 14),
                ],
                if (_error != null) ...[
                  Text(
                    _error!,
                    style: TextStyle(fontSize: 12, color: palette.accent),
                  ),
                  const SizedBox(height: 8),
                ],
                FilledButton(
                  onPressed: _submit,
                  child: const Text('提交选择'),
                ),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('稍后处理'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildField(AppPalette palette, Map<String, dynamic> field) {
    final key = _keyOf(field);
    final type = (field['type'] ?? 'string').toString();
    final title = (field['title'] ?? key).toString();
    final description = (field['description'] ?? '').toString();
    final required = field['required'] == true;

    if (type == 'multiselect' ||
        (type == 'string' &&
            field['options'] is List &&
            (field['options'] as List).isNotEmpty)) {
      return _buildOptions(palette, field, key, title, description, required,
          multi: type == 'multiselect');
    }
    if (type == 'boolean') {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _fieldTitle(palette, title, description, required),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(
              _values[key] == true ? '是' : '否',
              style: TextStyle(fontSize: 12.5, color: palette.ink),
            ),
            value: _values[key] == true,
            onChanged: (value) {
              setState(() => _values[key] = value);
            },
          ),
        ],
      );
    }
    if (type == 'external') {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: palette.background,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: palette.line),
        ),
        child: Text(
          '「$title」需要在外部页面完成。',
          style: TextStyle(fontSize: 11.5, color: palette.muted),
        ),
      );
    }

    final numeric = type == 'number' || type == 'integer';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _fieldTitle(palette, title, description, required),
        TextField(
          controller: _text[key],
          keyboardType: numeric
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          style: const TextStyle(fontSize: 13),
          decoration: InputDecoration(
            hintText: (field['placeholder'] ?? '').toString(),
            isDense: true,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildOptions(
    AppPalette palette,
    Map<String, dynamic> field,
    String key,
    String title,
    String description,
    bool required, {
    required bool multi,
  }) {
    final options = ((field['options'] as List?) ?? const [])
        .whereType<Map>()
        .map((option) => Map<String, dynamic>.from(option))
        .toList();
    final selected = _selected[key] ?? const <String>[];
    final single = (_values[key] ?? '').toString();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _fieldTitle(palette, title, description, required),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final option in options)
              multi
                  ? FilterChip(
                      label: Text(
                        (option['label'] ?? option['value'] ?? '').toString(),
                        style: const TextStyle(fontSize: 12),
                      ),
                      selected: selected.contains(
                        (option['value'] ?? option['label'] ?? '').toString(),
                      ),
                      onSelected: (checked) {
                        final value = (option['value'] ?? option['label'] ?? '')
                            .toString();
                        setState(() {
                          final list = _selected.putIfAbsent(key, () => []);
                          if (checked) {
                            list.add(value);
                          } else {
                            list.remove(value);
                          }
                        });
                      },
                    )
                  : ChoiceChip(
                      label: Text(
                        (option['label'] ?? option['value'] ?? '').toString(),
                        style: const TextStyle(fontSize: 12),
                      ),
                      selected: single ==
                          (option['value'] ?? option['label'] ?? '').toString(),
                      onSelected: (_) {
                        setState(() {
                          _values[key] =
                              (option['value'] ?? option['label'] ?? '')
                                  .toString();
                        });
                      },
                    ),
          ],
        ),
        if (field['custom'] == true) ...[
          const SizedBox(height: 8),
          TextField(
            controller: _custom[key],
            style: const TextStyle(fontSize: 13),
            decoration: InputDecoration(
              hintText: '其他（手动输入）',
              isDense: true,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _fieldTitle(
    AppPalette palette,
    String title,
    String description,
    bool required,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            required ? '$title *' : title,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: palette.ink,
            ),
          ),
          if (description.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                description,
                style: TextStyle(fontSize: 10.5, color: palette.muted),
              ),
            ),
        ],
      ),
    );
  }
}
