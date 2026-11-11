import Flutter
import MediaPlayer
import receive_sharing_intent
import UIKit
import UserNotifications
import Vision

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var mediaChannel: FlutterMethodChannel?
  private var mediaCommandsConfigured = false

  /// Share-extension URL captured before Flutter attached its event listener.
  /// SceneDelegate fills this on a cold start; Dart replays it through the
  /// omniaide/share_intent channel.
  static var pendingShareUrl: URL?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // iOS 27 requires the UIScene lifecycle. With a scene manifest UIKit no longer
    // loads Main.storyboard automatically, so create the Flutter window here before
    // registering plugins. SceneDelegate attaches this window to the active scene.
    if window == nil {
      let window = UIWindow(frame: UIScreen.main.bounds)
      window.rootViewController =
        UIStoryboard(name: "Main", bundle: nil).instantiateInitialViewController()
      self.window = window
    }

    if #available(iOS 10.0, *) {
      UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    }

    GeneratedPluginRegistrant.register(with: self)
    setupMediaChannel()
    setupOcrChannel()
    setupClipboardChannel()
    setupShareChannel()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  // Fallback for the non-scene lifecycle; SceneDelegate handles the scene path.
  override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    if SwiftReceiveSharingIntentPlugin.instance.hasMatchingSchemePrefix(url: url) {
      return SwiftReceiveSharingIntentPlugin.instance.application(app, open: url, options: options)
    }
    return super.application(app, open: url, options: options)
  }

  private func setupClipboardChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/clipboard",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "readImage" else {
        result(FlutterMethodNotImplemented)
        return
      }
      let pasteboard = UIPasteboard.general
      guard pasteboard.hasImages, let image = pasteboard.image else {
        result(nil)
        return
      }
      var data = image.pngData()
      var mime = "image/png"
      var name = "clipboard.png"
      if let png = data, png.count > 20 * 1024 * 1024,
         let jpeg = image.jpegData(compressionQuality: 0.85) {
        data = jpeg
        mime = "image/jpeg"
        name = "clipboard.jpg"
      }
      guard let payload = data else {
        result(nil)
        return
      }
      result([
        "bytes": FlutterStandardTypedData(bytes: payload),
        "mime": mime,
        "name": name,
      ])
    }
  }

  private func setupShareChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/share_intent",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "replayPendingUrl":
        guard let url = AppDelegate.pendingShareUrl else {
          result(false)
          return
        }
        AppDelegate.pendingShareUrl = nil
        let handled = SwiftReceiveSharingIntentPlugin.instance.application(
          UIApplication.shared, open: url)
        NSLog("[share] replay url=%@ handled=%d", url.absoluteString, handled ? 1 : 0)
        result(handled)
      case "takePendingShareJson":
        result(AppDelegate.pendingShareJson())
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// Fallback for the cold-start race where the share URL is replayed before
  /// the Dart event channel is listening: hand back the raw shared payload.
  private static func pendingShareJson() -> String? {
    let groupId = Bundle.main.object(forInfoDictionaryKey: "AppGroupId") as? String
      ?? "group.\(Bundle.main.bundleIdentifier!)"
    guard let defaults = UserDefaults(suiteName: groupId),
          let data = defaults.data(forKey: "ShareKey"),
          let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return nil }

    let normalized: [[String: Any]] = items.map { item in
      var copy = item
      for key in ["path", "thumbnail"] {
        if let value = copy[key] as? String, value.hasPrefix("file://") {
          copy[key] = value.replacingOccurrences(of: "file://", with: "")
        }
      }
      return copy
    }
    guard let out = try? JSONSerialization.data(withJSONObject: normalized) else {
      return nil
    }
    return String(data: out, encoding: .utf8)
  }

  private func setupOcrChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/ocr",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "recognize",
            let args = call.arguments as? [String: Any],
            let path = args["path"] as? String else {
        result(FlutterMethodNotImplemented)
        return
      }
      DispatchQueue.global(qos: .userInitiated).async {
        do {
          let handler = VNImageRequestHandler(
            url: URL(fileURLWithPath: path),
            options: [:]
          )
          let request = VNRecognizeTextRequest()
          request.recognitionLevel = .accurate
          request.usesLanguageCorrection = true
          request.recognitionLanguages = ["zh-Hans", "en-US"]
          try handler.perform([request])
          let lines = (request.results ?? []).compactMap {
            $0.topCandidates(1).first?.string
          }
          DispatchQueue.main.async {
            result(lines.joined(separator: "\n"))
          }
        } catch {
          DispatchQueue.main.async {
            result(
              FlutterError(
                code: "ocr_failed",
                message: error.localizedDescription,
                details: nil
              )
            )
          }
        }
      }
    }
  }

  private func setupMediaChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/media",
      binaryMessenger: controller.binaryMessenger
    )
    mediaChannel = channel
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self = self else {
        result(nil)
        return
      }
      switch call.method {
      case "update":
        self.updateNowPlaying(call.arguments as? [String: Any] ?? [:])
        result(nil)
      case "clear":
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        if #available(iOS 13.0, *) {
          MPNowPlayingInfoCenter.default().playbackState = .stopped
        }
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
    setupRemoteCommands()
  }

  private func setupRemoteCommands() {
    guard !mediaCommandsConfigured else { return }
    mediaCommandsConfigured = true
    let center = MPRemoteCommandCenter.shared()

    func forward(_ command: String, arguments: Any? = nil) -> MPRemoteCommandHandlerStatus {
      DispatchQueue.main.async { [weak self] in
        self?.mediaChannel?.invokeMethod(command, arguments: arguments)
      }
      return .success
    }

    center.playCommand.isEnabled = true
    center.playCommand.addTarget { _ in forward("play") }

    center.pauseCommand.isEnabled = true
    center.pauseCommand.addTarget { _ in forward("pause") }

    center.togglePlayPauseCommand.isEnabled = true
    center.togglePlayPauseCommand.addTarget { _ in forward("toggle") }

    center.nextTrackCommand.isEnabled = true
    center.nextTrackCommand.addTarget { _ in forward("next") }

    center.previousTrackCommand.isEnabled = true
    center.previousTrackCommand.addTarget { _ in forward("previous") }

    center.changePlaybackPositionCommand.isEnabled = true
    center.changePlaybackPositionCommand.addTarget { event in
      guard let seek = event as? MPChangePlaybackPositionCommandEvent else {
        return .commandFailed
      }
      return forward("seek", arguments: ["position": seek.positionTime])
    }
  }

  private func updateNowPlaying(_ args: [String: Any]) {
    var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
    info[MPMediaItemPropertyTitle] = (args["title"] as? String) ?? "OmniAide"
    info[MPMediaItemPropertyArtist] = (args["artist"] as? String) ?? "OmniAide"
    if let duration = args["duration"] as? Double, duration > 0 {
      info[MPMediaItemPropertyPlaybackDuration] = duration
    }
    if let position = args["position"] as? Double {
      info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = position
    }
    let playing = (args["playing"] as? Bool) ?? false
    info[MPNowPlayingInfoPropertyPlaybackRate] = playing ? 1.0 : 0.0
    MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    if #available(iOS 13.0, *) {
      MPNowPlayingInfoCenter.default().playbackState = playing ? .playing : .paused
    }
  }
}
