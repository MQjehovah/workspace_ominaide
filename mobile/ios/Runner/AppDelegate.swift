import Flutter
import MediaPlayer
import UIKit
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var mediaChannel: FlutterMethodChannel?
  private var mediaCommandsConfigured = false

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
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
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
  }
}
