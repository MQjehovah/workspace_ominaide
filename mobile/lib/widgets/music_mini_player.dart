import 'package:flutter/material.dart';

import '../screens/music_screen.dart';
import '../services/music_player_service.dart';
import '../theme/app_theme.dart';

/// Compact now-playing bar shown above the tab bar.
class MusicMiniPlayer extends StatelessWidget {
  const MusicMiniPlayer({super.key});

  @override
  Widget build(BuildContext context) {
    final player = MusicPlayerService();
    return AnimatedBuilder(
      animation: player,
      builder: (context, _) {
        final song = player.current;
        if (song == null) return const SizedBox.shrink();
        final palette = AppPalette.of(context);
        final duration = player.duration.inMilliseconds;
        final progress = duration > 0
            ? (player.position.inMilliseconds / duration).clamp(0.0, 1.0)
            : 0.0;
        return Material(
          color: palette.card,
          child: InkWell(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const MusicScreen()),
            ),
            child: Container(
              decoration: BoxDecoration(
                border: Border(top: BorderSide(color: palette.line)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  LinearProgressIndicator(
                    value: progress,
                    minHeight: 2,
                    backgroundColor: palette.line,
                    color: palette.primary,
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 5, 6, 5),
                    child: Row(
                      children: [
                        Container(
                          width: 34,
                          height: 34,
                          decoration: BoxDecoration(
                            color: palette.primarySoft,
                            borderRadius: BorderRadius.circular(9),
                          ),
                          child: Icon(
                            Icons.music_note_rounded,
                            size: 18,
                            color: palette.primary,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                (song['name'] ?? '音乐').toString(),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                  color: palette.ink,
                                ),
                              ),
                              const SizedBox(height: 1),
                              Text(
                                'OmniAide · ${player.modeLabel}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 10,
                                  color: palette.muted,
                                ),
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          visualDensity: VisualDensity.compact,
                          onPressed: player.buffering ? null : player.toggle,
                          icon: player.buffering
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Icon(
                                  player.playing
                                      ? Icons.pause_rounded
                                      : Icons.play_arrow_rounded,
                                  color: palette.primary,
                                ),
                        ),
                        IconButton(
                          visualDensity: VisualDensity.compact,
                          onPressed: player.next,
                          icon: Icon(
                            Icons.skip_next_rounded,
                            color: palette.ink,
                          ),
                        ),
                        IconButton(
                          visualDensity: VisualDensity.compact,
                          tooltip: '关闭播放器',
                          onPressed: player.close,
                          icon: Icon(
                            Icons.close_rounded,
                            size: 18,
                            color: palette.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
