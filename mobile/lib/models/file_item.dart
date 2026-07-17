class FileItem {
  final int id;
  final String originalName;
  final bool isFolder;
  final String folderPath;
  final int size;
  final String? mimeType;
  final String createdAt;

  FileItem({
    required this.id,
    required this.originalName,
    this.isFolder = false,
    this.folderPath = '/',
    this.size = 0,
    this.mimeType,
    this.createdAt = '',
  });

  factory FileItem.fromJson(Map<String, dynamic> json) {
    return FileItem(
      id: json['id'] ?? 0,
      originalName: json['original_name'] ?? '',
      isFolder: json['is_folder'] ?? false,
      folderPath: json['folder_path'] ?? '/',
      size: json['size'] ?? 0,
      mimeType: json['mime_type'],
      createdAt: json['created_at'] ?? '',
    );
  }

  String get sizeFormatted {
    if (size < 1024) return '$size B';
    if (size < 1024 * 1024) return '${(size / 1024).toStringAsFixed(1)} KB';
    return '${(size / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
