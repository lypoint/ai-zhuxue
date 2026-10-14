import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    let controller = window?.rootViewController as! FlutterViewController
    FlutterMethodChannel(name: "ai.zhuxue/one_tap", binaryMessenger: controller.binaryMessenger)
      .setMethodCallHandler { call, result in
        let sdk = TXCommonHandler.sharedInstance()
        switch call.method {
        case "isAvailable":
          let key = (call.arguments as? [String: String])?["sdkKey"] ?? ""
          guard !key.isEmpty else { result(false); return }
          sdk.setAuthSDKInfo(key) { setup in
            guard String(describing: setup["resultCode"] ?? "") == "600000" else {
              result(false)
              return
            }
            sdk.checkEnvAvailable(with: PNSAuthType(rawValue: 2)!, complete: { availability in
              result(String(describing: availability?["resultCode"] ?? "") == "600000")
            })
          }
        case "getLoginToken":
          var completed = false
          sdk.getLoginToken(withTimeout: 8, controller: controller, model: nil) { response in
            guard !completed else { return }
            let code = Int(String(describing: response["resultCode"] ?? "")) ?? -1
            if code == 600001 || code == 700002 || code == 700003 || code == 700004 {
              return // 授权页事件，继续等待最终取号结果。
            }
            completed = true
            sdk.cancelLoginVC(animated: true, complete: nil)
            if code == 600000, let token = response["token"] as? String, !token.isEmpty {
              result(token)
            } else {
              result(FlutterError(code: "ONE_TAP_UNAVAILABLE", message: "请使用短信验证码登录", details: nil))
            }
          }
        default:
          result(FlutterMethodNotImplemented)
        }
      }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
