import Foundation
import UIKit

@objc(ShareViewController)
class ShareViewController: RSIShareViewController {
    override func shouldAutoRedirect() -> Bool {
        return true
    }
}
