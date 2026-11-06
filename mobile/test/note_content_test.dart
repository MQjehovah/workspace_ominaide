import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/services/api_service.dart';

void main() {
  final api = ApiService();

  test('keeps markdown unchanged', () {
    const markdown = '# 计划\n\n- 第一项\n- 第二项';
    expect(api.parseNoteMarkdown(markdown), markdown);
  });

  test('converts prose mirror headings, marks and lists to markdown', () {
    final raw = jsonEncode({
      'type': 'doc',
      'content': [
        {
          'type': 'heading',
          'attrs': {'level': 2},
          'content': [
            {'type': 'text', 'text': '计划'},
          ],
        },
        {
          'type': 'paragraph',
          'content': [
            {'type': 'text', 'text': '重点：'},
            {
              'type': 'text',
              'text': '预算',
              'marks': [
                {'type': 'bold'},
              ],
            },
          ],
        },
        {
          'type': 'bulletList',
          'content': [
            {
              'type': 'listItem',
              'content': [
                {
                  'type': 'paragraph',
                  'content': [
                    {'type': 'text', 'text': '第一项'},
                  ],
                },
              ],
            },
          ],
        },
      ],
    });

    final markdown = api.parseNoteMarkdown(raw);
    expect(markdown, contains('## 计划'));
    expect(markdown, contains('**预算**'));
    expect(markdown, contains('- 第一项'));
  });

  test('converts code blocks', () {
    final raw = jsonEncode({
      'type': 'doc',
      'content': [
        {
          'type': 'codeBlock',
          'attrs': {'language': 'dart'},
          'content': [
            {'type': 'text', 'text': 'print(1);'},
          ],
        },
      ],
    });
    final markdown = api.parseNoteMarkdown(raw);
    expect(markdown, contains('```dart'));
    expect(markdown, contains('print(1);'));
  });

  test('invalid json falls back to the original text', () {
    expect(api.parseNoteMarkdown('not json'), 'not json');
    expect(api.parseNoteMarkdown(''), '');
  });
}
