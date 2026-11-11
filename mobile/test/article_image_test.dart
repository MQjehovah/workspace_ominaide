import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniaide_mobile/widgets/article_image.dart';

const _headers = {'Accept': 'image/jpeg,image/png,image/*;q=0.8'};

void main() {
  testWidgets('article image fills the available width', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 300,
              child: ArticleImage(candidates: ['https://example.com/a.png']),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final image = tester.widget<Image>(find.byType(Image));
    // flutter_html's built-in renderer turned a 100% width into 100 logical
    // pixels; the custom renderer must always stretch to the content width.
    expect(tester.getSize(find.byType(Image)).width, closeTo(300, 1));
    expect((image.image as NetworkImage).headers, _headers);
  });

  testWidgets('flutter_html gives the image the full content width', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 320,
            child: Html(
              data: '<p>before</p><p><img src="https://example.com/a.png" /></p>'
                  '<p>after</p>',
              extensions: [
                ImageExtension(
                  builder: (context) => ArticleImage(
                    candidates: [context.attributes['src']!],
                  ),
                ),
              ],
              style: {
                'body': Style(margin: Margins.zero, padding: HtmlPaddings.zero),
                'img': Style(margin: Margins.only(top: 4, bottom: 4)),
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(tester.getSize(find.byType(Image)).width, closeTo(320, 1));
  });
}
