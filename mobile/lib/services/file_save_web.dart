// Web: file download via browser (returns a data URL usable as blob).
Future<String> writeBytesLocal(String filename, List<int> bytes) async {
  // On web, return a marker; the music screen uses downloadFile directly.
  return 'web://$filename';
}
