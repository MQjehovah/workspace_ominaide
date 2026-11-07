import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omniaide_mobile/services/token_utils.dart';

String _token(Map<String, dynamic> payload) {
  final header = base64Url.encode(utf8.encode('{"alg":"none"}')).replaceAll('=', '');
  final body = base64Url.encode(utf8.encode(jsonEncode(payload))).replaceAll('=', '');
  return '$header.$body.signature';
}

void main() {
  test('decodes payload', () {
    final token = _token({'sub': '1', 'exp': 2000000000});
    expect(decodeJwtPayload(token)?['sub'], '1');
  });

  test('detects tokens close to expiry', () {
    final now = DateTime.fromMillisecondsSinceEpoch(1000000 * 1000);
    final soon = _token({'exp': 1000000 + 30});
    final later = _token({'exp': 1000000 + 3600});
    expect(tokenNeedsRefresh(soon, now: now), isTrue);
    expect(tokenNeedsRefresh(later, now: now), isFalse);
    expect(tokenNeedsRefresh(null, now: now), isFalse);
    expect(tokenNeedsRefresh('garbage', now: now), isFalse);
  });
}
