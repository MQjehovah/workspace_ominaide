import ActivityKit
import Foundation

@available(iOS 16.1, *)
public struct CodingActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        public var title: String
        public var count: Int
        public var startedAt: Date
        public var status: String
        public var duration: String
        public var action: String

        public init(
            title: String,
            count: Int,
            startedAt: Date,
            status: String,
            duration: String = "",
            action: String = ""
        ) {
            self.title = title
            self.count = count
            self.startedAt = startedAt
            self.status = status
            self.duration = duration
            self.action = action
        }
    }

    public init() {}
}
