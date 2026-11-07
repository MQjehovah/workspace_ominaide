import 'dart:convert';

/// Decode a JWT payload without verifying its signature.
Map<String, dynamic>? decodeJwtPayload(String? token) {
  if (token == null || token.isEmpty) return null;
  final parts = token.split('.');
  if (parts.length < 2) return null;
  try {
    final normalized = base64Url.normalize(parts[1]);
    final raw = utf8.decode(base64Url.decode(normalized));
    final value = jsonDecode(raw);
    return value is Map<String, dynamic> ? value : null;
  } catch (_) {
    return null;
  }
}

/// True when the access token expires within [skew].
bool tokenNeedsRefresh(
  String? token, {
  Duration skew = const Duration(seconds: 60),
  DateTime? now,
}) {
  if (token == null || token.isEmpty) return false;
  final exp = decodeJwtPayload(token)?['exp'];
  if (exp is! num) return false;
  final expiry = DateTime.fromMillisecondsSinceEpoch(exp.toInt() * 1000);
  return expiry.isBefore((now ?? DateTime.now()).add(skew));
}
