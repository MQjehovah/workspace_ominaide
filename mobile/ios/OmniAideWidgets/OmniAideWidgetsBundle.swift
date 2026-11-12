import ActivityKit
import SwiftUI
import WidgetKit

@main
struct OmniAideWidgetsBundle: WidgetBundle {
    var body: some Widget {
        CodingLiveActivityWidget()
    }
}

private extension CodingActivityAttributes.ContentState {
    var isRunning: Bool { status == "running" }
    var isWaiting: Bool { status == "waiting" }
    var isFailed: Bool { status == "failed" }

    var accent: Color {
        if isWaiting { return Color(red: 0.96, green: 0.62, blue: 0.04) }
        if isFailed { return Color(red: 0.94, green: 0.35, blue: 0.30) }
        if status == "completed" { return Color(red: 0.20, green: 0.75, blue: 0.45) }
        if status == "interrupted" { return Color(red: 0.62, green: 0.65, blue: 0.72) }
        return Color(red: 0.35, green: 0.60, blue: 1.0)
    }

    var statusText: String {
        if isWaiting { return "等待你的选择" }
        if isFailed { return "执行失败" }
        if status == "completed" { return "已完成" }
        if status == "interrupted" { return "已停止" }
        return "运行中"
    }

    var symbol: String {
        if isWaiting { return "questionmark.circle.fill" }
        if isFailed { return "exclamationmark.triangle.fill" }
        if status == "completed" { return "checkmark.circle.fill" }
        if status == "interrupted" { return "stop.circle.fill" }
        return "terminal.fill"
    }
}

struct CodingLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: CodingActivityAttributes.self) { context in
            LockScreenRunView(state: context.state)
                .activityBackgroundTint(Color(red: 0.055, green: 0.07, blue: 0.11))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 7) {
                        StatusIcon(state: context.state, size: 17)
                        Text(context.state.statusText)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(context.state.accent)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    RunClock(state: context.state, compact: false)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.title)
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                        .foregroundStyle(.white)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 5) {
                        if context.state.isWaiting && !context.state.action.isEmpty {
                            Text(context.state.action)
                                .font(.caption2.weight(.medium))
                                .lineLimit(1)
                                .foregroundStyle(context.state.accent)
                        }
                        HStack(spacing: 6) {
                            Circle()
                                .fill(context.state.accent)
                                .frame(width: 5, height: 5)
                            Text(context.state.count > 1
                                 ? "\(context.state.count) 个任务"
                                 : "OmniAide")
                                .font(.caption2)
                                .foregroundStyle(.white.opacity(0.55))
                            Spacer()
                            Text(context.state.isRunning ? "实时同步" : "点按回到 App")
                                .font(.caption2)
                                .foregroundStyle(.white.opacity(0.4))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } compactLeading: {
                StatusBadge(state: context.state)
            } compactTrailing: {
                CompactClock(state: context.state)
            } minimal: {
                StatusIcon(state: context.state, size: 14)
            }
            .keylineTint(context.state.accent)
        }
    }
}

private struct StatusIcon: View {
    let state: CodingActivityAttributes.ContentState
    let size: CGFloat

    var body: some View {
        Image(systemName: state.symbol)
            .font(.system(size: size, weight: .semibold))
            .foregroundStyle(state.accent)
    }
}

private struct StatusBadge: View {
    let state: CodingActivityAttributes.ContentState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            StatusIcon(state: state, size: 14)
            if state.count > 1 {
                Text("\(state.count)")
                    .font(.system(size: 8, weight: .heavy))
                    .foregroundStyle(.white)
                    .padding(2)
                    .background(Circle().fill(state.accent))
                    .offset(x: 7, y: -6)
            }
        }
        .frame(width: 18, height: 18)
    }
}

private struct CompactClock: View {
    let state: CodingActivityAttributes.ContentState

    var body: some View {
        Group {
            if state.isRunning {
                Text(timerInterval: state.startedAt...Date.distantFuture, countsDown: false)
                    .font(.caption2.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.white)
            } else if state.isWaiting {
                Text("待选")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(state.accent)
            } else {
                Text(state.isFailed ? "失败" : "完成")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(state.accent)
            }
        }
        .lineLimit(1)
        .minimumScaleFactor(0.75)
        .frame(width: 34, alignment: .trailing)
    }
}

private struct RunClock: View {
    let state: CodingActivityAttributes.ContentState
    let compact: Bool

    var body: some View {
        if state.isRunning {
            Text(timerInterval: state.startedAt...Date.distantFuture, countsDown: false)
                .font(clockFont)
                .monospacedDigit()
                .foregroundStyle(.white)
        } else if state.isWaiting {
            Text(compact ? "待选" : "待选择")
                .font(compact ? .caption2.weight(.bold) : .title3.weight(.semibold))
                .foregroundStyle(state.accent)
        } else {
            Text(state.duration.isEmpty ? state.statusText : state.duration)
                .font(clockFont)
                .monospacedDigit()
                .foregroundStyle(state.accent)
        }
    }

    private var clockFont: Font {
        compact ? .caption.monospacedDigit().weight(.semibold) : .title3.monospacedDigit()
    }
}

private struct LockScreenRunView: View {
    let state: CodingActivityAttributes.ContentState

    var body: some View {
        HStack(spacing: 13) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(state.accent.opacity(0.16))
                    .frame(width: 42, height: 42)
                StatusIcon(state: state, size: 21)
            }
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 5) {
                    Circle()
                        .fill(state.accent)
                        .frame(width: 5, height: 5)
                    Text(state.statusText)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(state.accent)
                    if state.count > 1 {
                        Text("· \(state.count) 个任务")
                            .font(.caption2)
                            .foregroundStyle(.white.opacity(0.45))
                    }
                }
                Text(state.title)
                    .font(.headline.weight(.semibold))
                    .lineLimit(1)
                    .foregroundStyle(.white)
                if state.isWaiting && !state.action.isEmpty {
                    Text(state.action)
                        .font(.caption2)
                        .lineLimit(1)
                        .foregroundStyle(state.accent.opacity(0.9))
                } else {
                    Text(state.isRunning ? "OpenCode 正在桌面端执行" : "OpenCode")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.45))
                }
            }
            Spacer(minLength: 6)
            RunClock(state: state, compact: false)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
    }
}
