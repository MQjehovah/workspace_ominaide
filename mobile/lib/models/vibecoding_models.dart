class VibecodingDevice {
  final String deviceId;
  final String name;
  final bool connected;
  final String? activeTask;

  VibecodingDevice({
    required this.deviceId,
    required this.name,
    required this.connected,
    this.activeTask,
  });

  factory VibecodingDevice.fromJson(Map<String, dynamic> j) => VibecodingDevice(
        deviceId: (j['device_id'] ?? '').toString(),
        name: (j['name'] ?? j['device_id'] ?? '').toString(),
        connected: j['connected'] == true,
        activeTask: j['active_task']?.toString(),
      );
}

class VibecodingProject {
  final String name;
  final String path;
  final String type;

  VibecodingProject({required this.name, required this.path, this.type = ''});

  factory VibecodingProject.fromJson(Map<String, dynamic> j) => VibecodingProject(
        name: (j['name'] ?? '').toString(),
        path: (j['path'] ?? '').toString(),
        type: (j['type'] ?? '').toString(),
      );
}

enum VibeStatus { pending, running, done, failed, cancelled, unknown }

VibeStatus vibeStatusOf(String? s) {
  switch (s) {
    case 'pending':
      return VibeStatus.pending;
    case 'running':
      return VibeStatus.running;
    case 'done':
      return VibeStatus.done;
    case 'failed':
      return VibeStatus.failed;
    case 'cancelled':
      return VibeStatus.cancelled;
    default:
      return VibeStatus.unknown;
  }
}

class VibecodingTask {
  final String taskId;
  final String? deviceId;
  final String? tool;
  final String? project;
  final String? projectName;
  final String? source;
  final String input;
  VibeStatus status;
  final int? startedTs;
  int? endedTs;
  int? durationMs;
  int? code;
  String output;
  String? error;

  VibecodingTask({
    required this.taskId,
    this.deviceId,
    this.tool,
    this.project,
    this.projectName,
    this.source,
    this.input = '',
    this.status = VibeStatus.pending,
    this.startedTs,
    this.endedTs,
    this.durationMs,
    this.code,
    this.output = '',
    this.error,
  });

  factory VibecodingTask.fromJson(Map<String, dynamic> j) => VibecodingTask(
        taskId: (j['task_id'] ?? '').toString(),
        deviceId: j['device_id']?.toString(),
        tool: j['tool']?.toString(),
        project: j['project']?.toString(),
        projectName: j['project_name']?.toString(),
        source: j['source']?.toString(),
        input: (j['input'] ?? '').toString(),
        status: vibeStatusOf(j['status']?.toString()),
        startedTs: (j['started_ts'] as num?)?.toInt(),
        endedTs: (j['ended_ts'] as num?)?.toInt(),
        durationMs: (j['duration_ms'] as num?)?.toInt(),
        code: (j['code'] as num?)?.toInt(),
        output: (j['output'] ?? '').toString(),
        error: j['error']?.toString(),
      );

  bool get isRunning => status == VibeStatus.running || status == VibeStatus.pending;
}

/// A structured event in a task's live timeline (from WS task.event).
class VibeEvent {
  final String event; // started/milestone/output/tool/file/done/failed
  final Map<String, dynamic> data;
  final int ts;

  VibeEvent({required this.event, required this.data, required this.ts});

  factory VibeEvent.fromWs(Map<String, dynamic> msg) => VibeEvent(
        event: (msg['event'] ?? '').toString(),
        data: Map<String, dynamic>.from(msg['data'] ?? {}),
        ts: (msg['ts'] as num?)?.toInt() ?? DateTime.now().millisecondsSinceEpoch,
      );

  String? get stage => data['stage']?.toString();
  String? get chunk => data['chunk']?.toString();
  String? get toolName => data['name']?.toString();
  String? get detail => data['detail']?.toString();
  String? get path => data['path']?.toString();
  String? get action => data['action']?.toString();
}
