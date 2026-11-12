import ActivityKit
import SwiftUI
import WidgetKit

@main
struct OmniAideWidgetsBundle: WidgetBundle {
    var body: some Widget {
        CodingLiveActivityWidget()
    }
}

struct CodingLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: CodingActivityAttributes.self) { context in
            LockScreenRunView(state: context.state)
                .activityBackgroundTint(Color(red: 0.07, green: 0.09, blue: 0.14))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 7) {
                        RunIcon()
                        Text(context.state.count > 1
                             ? "\(context.state.count) 个任务"
                             : "OpenCode")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.85))
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    RunClock(state: context.state, compact: false)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(context.state.title)
                            .font(.subheadline.weight(.semibold))
                            .lineLimit(1)
                            .foregroundStyle(.white)
                        Text(context.state.status == "running"
                             ? "在桌面端运行中"
                             : context.state.status == "failed" ? "执行失败" : "已完成")
                            .font(.caption2)
                            .foregroundStyle(.white.opacity(0.6))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } compactLeading: {
                RunIcon()
            } compactTrailing: {
                Text("\(context.state.count)")
                    .font(.caption2.weight(.bold))
                    .monospacedDigit()
            } minimal: {
                RunIcon()
            }
            .keylineTint(Color(red: 0.28, green: 0.55, blue: 1.0))
        }
    }
}

private struct RunIcon: View {
    var body: some View {
        Image(systemName: "terminal.fill")
            .font(.system(size: 12, weight: .bold))
            .foregroundStyle(Color(red: 0.55, green: 0.75, blue: 1.0))
    }
}

private struct RunClock: View {
    let state: CodingActivityAttributes.ContentState
    let compact: Bool

    var body: some View {
        if state.status == "running" {
            Text(timerInterval: state.startedAt...Date.distantFuture, countsDown: false)
                .font(compact ? .caption.monospacedDigit() : .title3.monospacedDigit())
                .foregroundStyle(.white)
        } else if state.status == "waiting" {
            Text("待选择")
                .font(compact ? .caption : .title3)
                .foregroundStyle(Color.orange)
        } else {
            Text(state.duration.isEmpty ? (state.status == "failed" ? "失败" : "完成") : state.duration)
                .font(compact ? .caption.monospacedDigit() : .title3.monospacedDigit())
                .foregroundStyle(state.status == "failed" ? Color.orange : Color.green)
        }
    }
}

private struct LockScreenRunView: View {
    let state: CodingActivityAttributes.ContentState

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color(red: 0.15, green: 0.22, blue: 0.36))
                    .frame(width: 36, height: 36)
                RunIcon()
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(state.status == "waiting"
                 ? "OpenCode 需要你的选择"
                 : state.count > 1 ? "\(state.count) 个 OpenCode 任务" : "OpenCode 运行中")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.6))
                Text(state.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .foregroundStyle(.white)
            }
            Spacer(minLength: 8)
            RunClock(state: state, compact: false)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}
