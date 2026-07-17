import 'package:flutter_test/flutter_test.dart';
import 'package:omniaide_mobile/main.dart';

void main() {
  testWidgets('App loads', (WidgetTester tester) async {
    await tester.pumpWidget(const OmniAideApp());
    expect(find.byType(OmniAideApp), findsOneWidget);
  });
}
