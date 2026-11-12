import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omniaide_mobile/models/opencode_models.dart';
import 'package:omniaide_mobile/widgets/opencode_form_sheet.dart';

void main() {
  OpenCodeForm buildForm() => OpenCodeForm.fromJson({
        'form': {
          'id': 'frm_test',
          'sessionID': 'ses_test',
          'title': '请选择继续方式',
          'fields': [
            {
              'key': 'choice',
              'type': 'string',
              'title': '下一步',
              'required': true,
              'options': [
                {'value': 'a', 'label': '选项 A'},
                {'value': 'b', 'label': '选项 B'},
              ],
            },
          ],
        },
      });

  test('parses an OpenCode form event payload', () {
    final form = buildForm();
    expect(form.formId, 'frm_test');
    expect(form.title, '请选择继续方式');
    expect(form.fields, hasLength(1));
    expect(form.fields.first['key'], 'choice');
  });

  testWidgets('ask-user sheet returns the selected option', (tester) async {
    Map<String, dynamic>? answer;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () async {
                  answer = await Navigator.of(context).push<Map<String, dynamic>>(
                    MaterialPageRoute(
                      builder: (_) => Scaffold(
                        body: OpenCodeFormSheet(form: buildForm()),
                      ),
                    ),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('请选择继续方式'), findsOneWidget);
    await tester.tap(find.text('选项 A'));
    await tester.pump();
    await tester.tap(find.text('提交选择'));
    await tester.pumpAndSettle();
    expect(answer, {'choice': 'a'});
  });
}
