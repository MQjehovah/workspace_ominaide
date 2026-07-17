import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../models/file_item.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _chatController = TextEditingController();
  final _messages = <Map<String, String>>[];
  bool _chatLoading = false;
  List<FileItem> _recentFiles = [];
  bool _loadingFiles = true;

  @override
  void initState() {
    super.initState();
    _loadRecent();
  }

  Future<void> _loadRecent() async {
    final files = await ApiService().listFiles();
    if (!mounted) return;
    setState(() { _recentFiles = files; _loadingFiles = false; });
  }

  Future<void> _sendChat() async {
    final text = _chatController.text.trim();
    if (text.isEmpty) return;
    _chatController.clear();
    setState(() {
      _messages.add({'role': 'user', 'text': text});
      _chatLoading = true;
    });
    try {
      final reply = await ApiService().callMCP('get_system_context', {});
      if (!mounted) return;
      setState(() { _messages.add({'role': 'ai', 'text': reply}); _chatLoading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _messages.add({'role': 'ai', 'text': '连接失败'}); _chatLoading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('OmniAide')),
      body: Column(
        children: [
          // AI Chat Input
          Container(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                TextField(
                  controller: _chatController,
                  decoration: InputDecoration(
                    hintText: '向 AI 提问...',
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                    suffixIcon: _chatLoading
                      ? const Padding(padding: EdgeInsets.all(14), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))
                      : IconButton(icon: const Icon(Icons.send), onPressed: _sendChat),
                  ),
                  onSubmitted: (_) => _sendChat(),
                ),
                if (_messages.isNotEmpty)
                  SizedBox(
                    height: 140,
                    child: ListView.builder(
                      padding: const EdgeInsets.only(top: 8),
                      itemCount: _messages.length,
                      itemBuilder: (_, i) {
                        final m = _messages[i];
                        final isUser = m['role'] == 'user';
                        return Align(
                          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 6),
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: isUser ? const Color(0xFF007AFF) : Colors.grey.shade100,
                              borderRadius: BorderRadius.only(
                                topLeft: const Radius.circular(12), topRight: const Radius.circular(12),
                                bottomLeft: isUser ? const Radius.circular(12) : Radius.zero,
                                bottomRight: isUser ? Radius.zero : const Radius.circular(12),
                              ),
                            ),
                            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                            child: Text(m['text'] ?? '', style: TextStyle(color: isUser ? Colors.white : Colors.black87, fontSize: 13)),
                          ),
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),

          // Quick Actions
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              _quickBtn(Icons.folder, '文件', () {}),
              const SizedBox(width: 12),
              _quickBtn(Icons.refresh, '刷新', _loadRecent),
            ]),
          ),
          const SizedBox(height: 16),

          // Recent Files
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              Text('最近文件', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
            ]),
          ),
          Expanded(
            child: _loadingFiles
              ? const Center(child: CircularProgressIndicator())
              : _recentFiles.isEmpty
                ? const Center(child: Text('暂无文件', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _recentFiles.length,
                    itemBuilder: (_, i) {
                      final f = _recentFiles[i];
                      return ListTile(
                        dense: true,
                        leading: Icon(f.isFolder ? Icons.folder : Icons.insert_drive_file, color: f.isFolder ? Colors.amber : Colors.blue),
                        title: Text(f.originalName, style: const TextStyle(fontSize: 14)),
                        subtitle: Text(f.sizeFormatted, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _quickBtn(IconData icon, String label, VoidCallback onTap) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            color: Colors.grey.shade50,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.grey.shade200),
          ),
          child: Column(children: [
            Icon(icon, color: const Color(0xFF007AFF)),
            const SizedBox(height: 6),
            Text(label, style: const TextStyle(fontSize: 12)),
          ]),
        ),
      ),
    );
  }
}
