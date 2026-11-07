import UIKit
import receive_sharing_intent

/// Bridges the legacy Flutter (pre-3.38) AppDelegate window into the iOS 27
/// UIScene lifecycle, which Apple now requires for apps built with the iOS 27 SDK.
///
/// It also forwards share-extension URLs to the host app. With the scene
/// lifecycle UIKit no longer calls UIApplicationDelegate's open-URL methods, so
/// the share extension would otherwise be unable to hand content to Flutter.
class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    guard let windowScene = scene as? UIWindowScene,
          let appDelegate = UIApplication.shared.delegate as? AppDelegate,
          let appWindow = appDelegate.window
    else { return }

    appWindow.windowScene = windowScene
    window = appWindow
    window?.makeKeyAndVisible()

    // Cold start from the share extension: remember the URL so Dart can replay
    // it once its event channel is listening.
    if let url = connectionOptions.urlContexts.first?.url,
       SwiftReceiveSharingIntentPlugin.instance.hasMatchingSchemePrefix(url: url) {
      AppDelegate.pendingShareUrl = url
    }
  }

  func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    guard let url = URLContexts.first?.url else { return }
    if SwiftReceiveSharingIntentPlugin.instance.hasMatchingSchemePrefix(url: url) {
      // App is already running: Flutter's listener is attached, deliver now.
      _ = SwiftReceiveSharingIntentPlugin.instance.application(
        UIApplication.shared, open: url)
    }
  }
}
