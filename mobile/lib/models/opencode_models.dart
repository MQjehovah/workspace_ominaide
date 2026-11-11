/// Models for remote OpenCode 2 sessions surfaced through the vibecoding
/// channel. The desktop plugin normalizes OpenCode's API into these shapes.
class OpenCodeSession {
  final String id;
  final String title;
  final String directory;
  final String agent;
  final String model;
  final String provider;
  final String outcome;
  final int created;
  final int updated;
  final bool busy;

  const OpenCodeSession({
    required this.id,
    required this.title,
    this.directory = '',
    this.agent = '',
    this.model = '',
    this.provider = '',
    this.outcome = '',
    this.created = 0,
    this.updated = 0,
    this.busy = false,
  });

  factory OpenCodeSession.fromJson(Map<String, dynamic> json) {
    return OpenCodeSession(
      id: (json['id'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      directory: (json['directory'] ?? '').toString(),
      agent: (json['agent'] ?? '').toString(),
      model: (json['model'] ?? '').toString(),
      provider: (json['provider'] ?? '').toString(),
      outcome: (json['outcome'] ?? '').toString(),
      created: (json['created'] as num?)?.toInt() ?? 0,
      updated: (json['updated'] as num?)?.toInt() ?? 0,
      busy: json['busy'] == true,
    );
  }

  DateTime? get updatedAt =>
      updated > 0 ? DateTime.fromMillisecondsSinceEpoch(updated) : null;
}

class OpenCodePart {
  final String type; // text / reasoning / tool / file
  final String text;
  final String name;
  final String status;
  final Map<String, dynamic> input;
  final String error;

  const OpenCodePart({
    required this.type,
    this.text = '',
    this.name = '',
    this.status = '',
    this.input = const {},
    this.error = '',
  });

  factory OpenCodePart.fromJson(Map<String, dynamic> json) {
    return OpenCodePart(
      type: (json['type'] ?? '').toString(),
      text: (json['text'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      input: json['input'] is Map
          ? Map<String, dynamic>.from(json['input'] as Map)
          : const {},
      error: (json['error'] ?? '').toString(),
    );
  }
}

class OpenCodeMessage {
  final String id;
  final String role; // user / assistant
  final String agent;
  final String model;
  final int time;
  final List<OpenCodePart> parts;

  const OpenCodeMessage({
    required this.id,
    required this.role,
    this.agent = '',
    this.model = '',
    this.time = 0,
    this.parts = const [],
  });

  factory OpenCodeMessage.fromJson(Map<String, dynamic> json) {
    final parts = (json['parts'] as List?)
            ?.whereType<Map>()
            .map((part) =>
                OpenCodePart.fromJson(Map<String, dynamic>.from(part)))
            .toList() ??
        const <OpenCodePart>[];
    return OpenCodeMessage(
      id: (json['id'] ?? '').toString(),
      role: (json['role'] ?? 'assistant').toString(),
      agent: (json['agent'] ?? '').toString(),
      model: (json['model'] ?? '').toString(),
      time: (json['time'] as num?)?.toInt() ?? 0,
      parts: parts,
    );
  }

  bool get isUser => role == 'user';

  String get text => parts
      .where((part) => part.type == 'text')
      .map((part) => part.text)
      .where((text) => text.trim().isNotEmpty)
      .join('\n\n');

  String get reasoning => parts
      .where((part) => part.type == 'reasoning')
      .map((part) => part.text)
      .where((text) => text.trim().isNotEmpty)
      .join('\n\n');

  List<OpenCodePart> get tools =>
      parts.where((part) => part.type == 'tool').toList();
}
