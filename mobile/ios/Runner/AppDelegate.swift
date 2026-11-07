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

  private func setupShareChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/share_intent",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "replayPendingUrl" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let url = AppDelegate.pendingShareUrl else {
        result(false)
        return
      }
      AppDelegate.pendingShareUrl = nil
      result(
        SwiftReceiveSharingIntentPlugin.instance.application(
          UIApplication.shared, open: url)
      )
    }
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
