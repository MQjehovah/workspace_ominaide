/// Default OmniAide server. The web app is deployed under `/ominaide/`, and the
/// backend API is mounted at `/ominaide/api`, so the mobile client's base URL
/// must include that path prefix.
const String kDefaultServerUrl = 'https://mqgeek.com/ominaide';

/// Normalize a user-entered server address: trim spaces, drop trailing slashes.
String normalizeServerUrl(String raw) {
  var value = raw.trim();
  while (value.length > 1 && value.endsWith('/')) {
    value = value.substring(0, value.length - 1);
  }
  return value;
}
