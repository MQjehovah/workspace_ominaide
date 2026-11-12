import ActivityKit
import Flutter
import Foundation
import UIKit

@available(iOS 16.2, *)
final class CodingLiveActivityManager {
    static let shared = CodingLiveActivityManager()

    private init() {}

    func sync(
        title: String,
        count: Int,
        startedAt: Date,
        status: String,
        action: String
    ) async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let state = CodingActivityAttributes.ContentState(
            title: title,
            count: count,
            startedAt: startedAt,
            status: status,
            action: action
        )
        let content = ActivityContent(state: state, staleDate: nil)
        let activities = Activity<CodingActivityAttributes>.activities
        if let activity = activities.first {
            // Clean up duplicates left over from a previous install/launch.
            for extra in activities.dropFirst() {
                await extra.end(nil, dismissalPolicy: .immediate)
            }
            await activity.update(content)
            return
        }
        do {
            _ = try Activity<CodingActivityAttributes>.request(
                attributes: CodingActivityAttributes(),
                content: content,
                pushType: nil
            )
        } catch {
            // Live Activities can be disabled by the user or restricted by the
            // system. The in-app bubble and notifications still work.
        }
    }

    func end(
        title: String,
        count: Int,
        startedAt: Date,
        status: String,
        duration: String
    ) async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let state = CodingActivityAttributes.ContentState(
            title: title,
            count: count,
            startedAt: startedAt,
            status: status,
            duration: duration
        )
        let content = ActivityContent(state: state, staleDate: nil)
        for activity in Activity<CodingActivityAttributes>.activities {
            await activity.end(
                content,
                dismissalPolicy: .after(Date().addingTimeInterval(8))
            )
        }
    }

    func endAll() async {
        for activity in Activity<CodingActivityAttributes>.activities {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }
}

func setupLiveActivityChannel(window: UIWindow?) {
    guard let root = window?.rootViewController as? FlutterViewController else {
        return
    }
    let channel = FlutterMethodChannel(
        name: "omniaide/live_activity",
        binaryMessenger: root.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
        guard #available(iOS 16.2, *) else {
            result(false)
            return
        }
        let args = call.arguments as? [String: Any] ?? [:]
        let title = args["title"] as? String ?? "OpenCode 会话"
        let count = (args["count"] as? NSNumber)?.intValue ?? 1
        let startedMs =
            (args["startedAt"] as? NSNumber)?.doubleValue
            ?? (Date().timeIntervalSince1970 * 1000)
        let startedAt = Date(timeIntervalSince1970: startedMs / 1000)
        let status = args["status"] as? String ?? "running"
        let duration = args["duration"] as? String ?? ""
        let action = args["action"] as? String ?? ""

        switch call.method {
        case "sync":
            Task { @MainActor in
                await CodingLiveActivityManager.shared.sync(
                    title: title,
                    count: count,
                    startedAt: startedAt,
                    status: status,
                    action: action
                )
                result(true)
            }
        case "end":
            Task { @MainActor in
                await CodingLiveActivityManager.shared.end(
                    title: title,
                    count: count,
                    startedAt: startedAt,
                    status: status,
                    duration: duration
                )
                result(true)
            }
        case "endAll":
            Task { @MainActor in
                await CodingLiveActivityManager.shared.endAll()
                result(true)
            }
        default:
            result(FlutterMethodNotImplemented)
        }
    }
}
