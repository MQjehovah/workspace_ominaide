import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
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

    GeneratedPluginRegistrant.register(with: self)
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
