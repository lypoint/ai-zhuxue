#!/usr/bin/env python3
"""Fixed channel entries and dependency/artifact isolation checks."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import zipfile
from check_telemetry import check as check_telemetry

ROOT = Path(__file__).resolve().parents[1]
SDK = {"wechat": "fluwx", "appstore": "in_app_purchase_storekit", "googleplay": "in_app_purchase_android"}


def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


def check(channel):
    package = ROOT / "app" / f"app_parent_{channel}"
    check_telemetry(package)
    names = {p["name"] for p in json.loads((package / ".dart_tool/package_config.json").read_text())["packages"]}
    payment_sdks = set(SDK.values()) | {"in_app_purchase"}
    assert names & payment_sdks == {SDK[channel]}, f"{channel}: leaked payment dependencies {names & payment_sdks}"
    for shared in ("app_parent", "app_core", "parent_store"):
        for source in (ROOT / "app" / shared / "lib").rglob("*.dart"):
            text = source.read_text()
            assert all(f"package:{sdk}/" not in text for sdk in payment_sdks), f"Shared library imports a payment SDK: {source}"
    assert (package / "pubspec.lock").is_file(), "Commit each channel's dependency lockfile"
    if channel == "googleplay":
        assert "google_sign_in" in names, "Google Play requires Google sign-in"
        assert "com.mobile.auth" not in (package / "android/app/src/main/AndroidManifest.xml").read_text()
        assert "fileTree" not in (package / "android/app/build.gradle.kts").read_text(), "Do not bundle phone SDK AARs"
    else:
        assert "google_sign_in" not in names, "Google login SDK must stay in its channel shell"
    if channel == "appstore":
        data = plistlib.loads((package / "ios/Runner/Info.plist").read_bytes())
        assert "weixin" not in repr(data).lower(), "App Store Info.plist contains WeChat routing"
        lock = (package / "ios/Podfile.lock").read_text()
        assert "fluwx" not in lock and "WechatOpenSDK" not in lock, "App Store pods contain WeChat"
        assert "in_app_purchase_storekit" in lock, "Run an iOS build/pod install first"
    print(f"{channel}: dependencies isolated ({SDK[channel]})")


def artifact(channel, path):
    if channel != "appstore":
        check_telemetry(ROOT / "app" / f"app_parent_{channel}", path)
    forbidden = {
        "wechat": (b"io/flutter/plugins/inapppurchase", b"io.flutter.plugins.inapppurchase", b"com/android/billingclient"),
        "googleplay": (b"com/jarvanmo/fluwx", b"com.jarvanmo.fluwx", b"com/tencent/mm/opensdk", b"com/mobile/auth", b"com.mobile.auth"),
        "appstore": (b"fluwx", b"WechatOpenSDK", b"WXApi"),
    }[channel]
    def inspect(name, data):
        for symbol in forbidden:
            assert symbol not in name.encode() and symbol not in data, f"Foreign payment SDK {symbol!r} in {name}"
    if path.is_dir():
        for file in path.rglob("*"):
            if file.is_file(): inspect(str(file.relative_to(path)), file.read_bytes())
    else:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist(): inspect(name, archive.read(name))
    print(f"{channel}: artifact isolation checked")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("channel", choices=SDK)
    parser.add_argument("--check", action="store_true", help="Check resolved dependencies without building")
    parser.add_argument("--artifact", type=Path, help="Inspect an existing APK/AAB/IPA/.app")
    parser.add_argument("--debug", action="store_true", help="Build locally without release credentials")
    args = parser.parse_args()
    channel = args.channel
    package = ROOT / "app" / f"app_parent_{channel}"
    if args.check or args.artifact:
        check(channel)
        if args.artifact: artifact(channel, args.artifact)
        return
    flutter = os.environ.get("FLUTTER", "flutter")
    run([flutter, "pub", "get", "--enforce-lockfile"], package)
    check(channel)
    options = []
    auth_key = "GOOGLE_SERVER_CLIENT_ID" if channel == "googleplay" else "ALIYUN_AUTH_SDK_KEY"
    for name in ("API_BASE", "PRIVACY_URL", "TERMS_URL", auth_key):
        if os.environ.get(name): options.append(f"--dart-define={name}={os.environ[name]}")
    if not args.debug:
        api_base = os.environ.get("API_BASE", "").strip()
        if not api_base.startswith("https://"):
            raise SystemExit("Set HTTPS API_BASE for store release (e.g. https://api.yourdomain.com)")
        if any(h in api_base for h in ("127.0.0.1", "localhost", "10.0.2.2")):
            raise SystemExit("API_BASE cannot point to loopback/local address for release build")
    if channel == "googleplay" and not args.debug:
        if not os.environ.get("GOOGLE_SERVER_CLIENT_ID", "").endswith(".apps.googleusercontent.com"):
            raise SystemExit("Set GOOGLE_SERVER_CLIENT_ID to the Google OAuth Web client ID")
    if channel == "wechat":
        app_id = os.environ.get("WECHAT_APP_ID", "")
        if not args.debug and (not app_id.startswith("wx") or "demo" in app_id):
            raise SystemExit("Set the real WECHAT_APP_ID for release")
        if not args.debug and f"app_id: {app_id}" not in (package / "pubspec.yaml").read_text():
            raise SystemExit("Update fluwx.app_id in the WeChat shell pubspec to the same release AppID")
        if app_id: options.append(f"--dart-define=WECHAT_APP_ID={app_id}")
    elif not args.debug:
        for name in ("PRIVACY_URL", "TERMS_URL"):
            if not os.environ.get(name, "").startswith("https://"):
                raise SystemExit(f"Set HTTPS {name} for store release")
    if channel == "appstore":
        if not args.debug and not os.environ.get("ALIYUN_AUTH_SDK_KEY"):
            raise SystemExit("Set ALIYUN_AUTH_SDK_KEY for this bundle ID")
        mode = ["ios", "--debug", "--no-codesign"] if args.debug else ["ipa", "--release"]
        run([flutter, "build", *mode, *options], package)
        output = package / "build/ios/iphoneos/Runner.app" if args.debug else next((package / "build/ios/ipa").glob("*.ipa"))
    else:
        if not args.debug and not (package / "android/key.properties").is_file():
            raise SystemExit("Configure android/key.properties and the channel's release signing key")
        mode = ["apk", "--debug"] if args.debug else ["appbundle", "--release"]
        run([flutter, "build", *mode, *options], package)
        output = package / ("build/app/outputs/flutter-apk/app-debug.apk" if args.debug else "build/app/outputs/bundle/release/app-release.aab")
    artifact(channel, output)
    print(output)


if __name__ == "__main__":
    main()
