import AVFoundation
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
  private var voiceAudioChannel: FlutterMethodChannel?
  private var voiceEngine: AVAudioEngine?
  private var voicePlayerNode: AVAudioPlayerNode?
  private var voiceFormat: AVAudioFormat?
  private var voiceChunkIndex = 0
  private var voiceTapInstalled = false
  private var voiceTapCount = 0
  private var voiceMicChunks = 0
  private var voiceConfigObserver: NSObjectProtocol?

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
    setupVoiceAudioChannel()
    setupShareChannel()
    setupLiveActivityChannel(window: window)
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

  /// Voice conversations keep AVAudioSession in .voiceChat mode so the
  /// platform AEC has a render reference. .voiceChat prefers the earpiece, so
  /// the route is overridden explicitly while the mode stays intact.
  private func setupVoiceAudioChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "omniaide/voice_audio",
      binaryMessenger: controller.binaryMessenger
    )
    voiceAudioChannel = channel
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self = self else { result(nil); return }
      let session = AVAudioSession.sharedInstance()
      do {
        switch call.method {
        case "speakerOn":
          // Never change category/active state here: voiceStart owns the
          // engine, and a category change restarts it (silencing capture).
          try session.overrideOutputAudioPort(.speaker)
          result(nil)
        case "speakerOff":
          try session.overrideOutputAudioPort(.none)
          result(nil)
        case "voiceStart":
          let args = call.arguments as? [String: Any]
          let cap = (args?["captureRate"] as? NSNumber)?.doubleValue ?? 16000
          let play = (args?["playbackRate"] as? NSNumber)?.doubleValue ?? 48000
          let aec = (args?["aec"] as? Bool) ?? true
          result(self.startVoiceEngine(captureRate: cap, playbackRate: play, useVoiceProcessing: aec))
        case "voiceStop":
          self.shutdownVoiceEngine()
          result(nil)
        case "voiceStats":
          if let engine = self.voiceEngine, !engine.isRunning {
            try? AVAudioSession.sharedInstance().setActive(true)
            try? engine.start()
          }
          result([
            "tapCount": self.voiceTapCount,
            "chunks": self.voiceMicChunks,
            "running": self.voiceEngine?.isRunning ?? false,
          ])
        case "playbackStart":
          // The engine and input tap are owned by voiceStart; nothing to do
          // unless playback starts before capture.
          if self.voiceEngine == nil {
            let args = call.arguments as? [String: Any]
            let rate = (args?["sampleRate"] as? NSNumber)?.doubleValue ?? 48000
            self.startVoiceEngine(captureRate: 16000, playbackRate: rate, useVoiceProcessing: false)
          }
          result(nil)
        case "playbackPush":
          guard let typed = call.arguments as? FlutterStandardTypedData else {
            result(FlutterError(code: "voice_audio", message: "PCM bytes required", details: nil))
            return
          }
          self.pushVoiceAudio(typed.data)
          result(nil)
        case "playbackStop":
          self.stopVoicePlayback()
          result(nil)
        default:
          result(FlutterMethodNotImplemented)
        }
      } catch {
        result(FlutterError(code: "voice_audio", message: "\(error)", details: nil))
      }
    }
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

  /// One AVAudioEngine owns both capture and playback. Voice processing on
  /// the input node can only cancel echo from audio rendered by the same
  /// engine, which is why a separate player engine kept feeding the assistant
  /// its own voice back as user input.
  private func startVoiceEngine(captureRate: Double, playbackRate: Double, useVoiceProcessing: Bool) -> [String: Any] {
    shutdownVoiceEngine()

    let session = AVAudioSession.sharedInstance()
    do {
      try session.setCategory(
        .playAndRecord,
        mode: .voiceChat,
        options: [.defaultToSpeaker, .allowBluetooth]
      )
      try session.setActive(true)
      try session.overrideOutputAudioPort(.speaker)
    } catch {
      return ["ok": false, "error": "audio session: \(error)"]
    }

    let engine = AVAudioEngine()
    voiceEngine = engine
    let input = engine.inputNode
    if useVoiceProcessing {
      do {
        try input.setVoiceProcessingEnabled(true)
      } catch {
        shutdownVoiceEngine()
        return ["ok": false, "error": "voice processing: \(error)"]
      }
    }

    let inputFormat = input.outputFormat(forBus: 0)
    guard inputFormat.channelCount > 0,
          inputFormat.sampleRate > 0,
          let playFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: playbackRate,
            channels: 1,
            interleaved: false
          ) else {
      shutdownVoiceEngine()
      return ["ok": false, "error": "unsupported audio formats"]
    }

    voiceTapCount = 0
    voiceMicChunks = 0
    input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
      self?.handleVoiceCapture(buffer)
    }
    voiceTapInstalled = true

    let player = AVAudioPlayerNode()
    engine.attach(player)
    engine.connect(player, to: engine.mainMixerNode, format: playFormat)
    engine.prepare()
    do {
      try engine.start()
    } catch {
      shutdownVoiceEngine()
      return ["ok": false, "error": "engine start: \(error)"]
    }
    voicePlayerNode = player
    voiceFormat = playFormat
    voiceChunkIndex = 0
    voiceConfigObserver = NotificationCenter.default.addObserver(
      forName: .AVAudioEngineConfigurationChange,
      object: engine,
      queue: .main
    ) { [weak self] _ in
      guard let self = self,
            let current = self.voiceEngine,
            current === engine,
            !current.isRunning else { return }
      try? AVAudioSession.sharedInstance().setActive(true)
      try? current.start()
    }
    return [
      "ok": true,
      "running": engine.isRunning,
      "inputRate": inputFormat.sampleRate,
      "channels": inputFormat.channelCount,
    ]
  }

  /// Manual downmix + linear resample to 16 kHz mono Int16. AVAudioConverter
  /// was silently producing no frames on some routes; this path is predictable
  /// and cheap at voice rates.
  private func handleVoiceCapture(_ buffer: AVAudioPCMBuffer) {
    voiceTapCount += 1
    let frames = Int(buffer.frameLength)
    guard frames > 0 else { return }
    let inRate = buffer.format.sampleRate
    let channels = Int(buffer.format.channelCount)
    guard inRate > 0, channels > 0 else { return }
    let outCount = max(1, Int(Double(frames) * 16000.0 / inRate))
    var out = [Int16](repeating: 0, count: outCount)

    if let floatData = buffer.floatChannelData {
      for i in 0..<outCount {
        let pos = Double(i) * inRate / 16000.0
        let idx = min(frames - 1, Int(pos))
        let frac = Float(pos - Double(idx))
        var sample: Float = 0
        for ch in 0..<channels { sample += floatData[ch][idx] }
        sample /= Float(channels)
        if idx + 1 < frames {
          var next: Float = 0
          for ch in 0..<channels { next += floatData[ch][idx + 1] }
          next /= Float(channels)
          sample += (next - sample) * frac
        }
        out[i] = Int16(max(-1, min(1, sample)) * 32767)
      }
    } else if let intData = buffer.int16ChannelData {
      for i in 0..<outCount {
        let pos = Double(i) * inRate / 16000.0
        let idx = min(frames - 1, Int(pos))
        let frac = Float(pos - Double(idx))
        var sample: Float = 0
        for ch in 0..<channels { sample += Float(intData[ch][idx]) }
        sample /= Float(channels)
        if idx + 1 < frames {
          var next: Float = 0
          for ch in 0..<channels { next += Float(intData[ch][idx + 1]) }
          next /= Float(channels)
          sample += (next - sample) * frac
        }
        out[i] = Int16(max(-1, min(1, sample / 32768.0)) * 32767)
      }
    } else {
      return
    }

    let data = out.withUnsafeBufferPointer { Data(buffer: $0) }
    voiceMicChunks += 1
    DispatchQueue.main.async { [weak self] in
      self?.voiceAudioChannel?.invokeMethod(
        "micChunk",
        arguments: FlutterStandardTypedData(bytes: data)
      )
    }
  }

  private func pushVoiceAudio(_ data: Data) {
    guard let engine = voiceEngine,
          let player = voicePlayerNode,
          let format = voiceFormat else { return }
    let frames = data.count / 2
    guard frames > 0,
          let buffer = AVAudioPCMBuffer(
            pcmFormat: format,
            frameCapacity: AVAudioFrameCount(frames)
          ) else { return }
    buffer.frameLength = AVAudioFrameCount(frames)
    data.withUnsafeBytes { raw in
      let src = raw.bindMemory(to: Int16.self)
      if let dst = buffer.floatChannelData?[0] {
        for i in 0..<frames {
          dst[i] = Float(src[i]) / 32768.0
        }
      }
    }
    if !engine.isRunning {
      try? engine.start()
    }
    player.scheduleBuffer(buffer)
    if !player.isPlaying {
      player.play()
    }
  }

  /// Stop only the answer audio; the capture tap and engine stay alive so the
  /// user can barge in immediately.
  private func stopVoicePlayback() {
    voicePlayerNode?.stop()
    voicePlayerNode?.reset()
  }

  private func shutdownVoiceEngine() {
    if let observer = voiceConfigObserver {
      NotificationCenter.default.removeObserver(observer)
      voiceConfigObserver = nil
    }
    if voiceTapInstalled, let engine = voiceEngine {
      engine.inputNode.removeTap(onBus: 0)
      voiceTapInstalled = false
    }
    voicePlayerNode?.stop()
    if let engine = voiceEngine, let player = voicePlayerNode {
      engine.detach(player)
    }
    voiceEngine?.stop()
    voiceEngine = nil
    voicePlayerNode = nil
    voiceFormat = nil
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
