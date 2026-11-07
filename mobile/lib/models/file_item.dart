class FileItem {
  final int id;
  final String originalName;
  final bool isFolder;
  final String folderPath;
  final int size;
  final String? mimeType;
  final String createdAt;
  final bool isFavorite;
  final List<String> tags;

  FileItem({
    required this.id,
    required this.originalName,
    this.isFolder = false,
    this.folderPath = '/',
    this.size = 0,
    this.mimeType,
    this.createdAt = '',
    this.isFavorite = false,
    this.tags = const [],
  });

  factory FileItem.fromJson(Map<String, dynamic> json) {
    final rawTags = json['tags'];
    return FileItem(
      id: json['id'] ?? 0,
      originalName: json['original_name'] ?? '',
      isFolder: json['is_folder'] ?? false,
      folderPath: json['folder_path'] ?? '/',
      size: json['size'] ?? 0,
      mimeType: json['mime_type'],
      createdAt: json['created_at'] ?? '',
      isFavorite: json['is_favorite'] == true,
      tags: rawTags is List ? rawTags.map((e) => e.toString()).toList() : const [],
    );
  }

  String get sizeFormatted {
    if (size < 1024) return '$size B';
    if (size < 1024 * 1024) return '${(size / 1024).toStringAsFixed(1)} KB';
    return '${(size / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
