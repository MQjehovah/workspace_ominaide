import UIKit

/// Bridges the legacy Flutter (pre-3.38) AppDelegate window into the iOS 27
/// UIScene lifecycle, which Apple now requires for apps built with the iOS 27 SDK.
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
  }
}
