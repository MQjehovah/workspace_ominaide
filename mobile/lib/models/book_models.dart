class Book {
  const Book({
    required this.id,
    required this.fileId,
    required this.title,
    this.author = '',
    this.format = 'txt',
    this.status = 'unread',
    this.progress = 0,
    this.position = 0,
    this.paragraphCount = 0,
    this.lastOpened,
  });

  final int id;
  final int fileId;
  final String title;
  final String author;
  final String format;
  final String status; // unread / reading / finished
  final double progress;
  final int position;
  final int paragraphCount;
  final DateTime? lastOpened;

  bool get isUnread => status == 'unread';
  bool get isFinished => status == 'finished';
  bool get isReading => status == 'reading';

  String get statusLabel {
    if (isFinished) return '已读完';
    if (isReading) return '在读';
    return '未读';
  }

  factory Book.fromJson(Map<String, dynamic> json) {
    return Book(
      id: (json['id'] as num?)?.toInt() ?? 0,
      fileId: (json['file_id'] as num?)?.toInt() ?? 0,
      title: (json['title'] ?? '未命名书籍').toString(),
      author: (json['author'] ?? '').toString(),
      format: (json['format'] ?? 'txt').toString(),
      status: (json['status'] ?? 'unread').toString(),
      progress: (json['progress'] as num?)?.toDouble() ?? 0,
      position: (json['position'] as num?)?.toInt() ?? 0,
      paragraphCount: (json['paragraph_count'] as num?)?.toInt() ?? 0,
      lastOpened: DateTime.tryParse((json['last_opened'] ?? '').toString()),
    );
  }
}

class BookBookmark {
  const BookBookmark({
    required this.id,
    required this.position,
    this.label = '',
    this.note = '',
    this.createdAt,
  });

  final int id;
  final int position;
  final String label;
  final String note;
  final DateTime? createdAt;

  factory BookBookmark.fromJson(Map<String, dynamic> json) {
    return BookBookmark(
      id: (json['id'] as num?)?.toInt() ?? 0,
      position: (json['position'] as num?)?.toInt() ?? 0,
      label: (json['label'] ?? '').toString(),
      note: (json['note'] ?? '').toString(),
      createdAt: DateTime.tryParse((json['created_at'] ?? '').toString()),
    );
  }
}

class BookDetail {
  const BookDetail({
    required this.book,
    required this.content,
    required this.bookmarks,
  });

  final Book book;
  final String content;
  final List<BookBookmark> bookmarks;

  factory BookDetail.fromJson(Map<String, dynamic> json) {
    final marks = (json['bookmarks'] as List?) ?? const [];
    return BookDetail(
      book: Book.fromJson(json),
      content: (json['content'] ?? '').toString(),
      bookmarks: marks
          .whereType<Map>()
          .map((item) => BookBookmark.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
    );
  }
}
