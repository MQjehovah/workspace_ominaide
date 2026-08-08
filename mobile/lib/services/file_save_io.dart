// IO: save downloaded bytes to a temp file for native platforms.
import 'dart:io';

Future<String> writeBytesLocal(String filename, List<int> bytes) async {
  final dir = Directory.systemTemp;
  final path = '${dir.path}/$filename';
  await File(path).writeAsBytes(bytes);
  return path;
}
