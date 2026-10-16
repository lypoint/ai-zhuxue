#!/usr/bin/env python3
"""Check that Firebase is confined to the Google Play channel shells."""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIREBASE = {"firebase_core", "firebase_analytics", "firebase_crashlytics", "play_telemetry"}


def check(package, artifact=None):
    package = Path(package)
    play = package.name.endswith("_googleplay")
    config = json.loads((package / ".dart_tool/package_config.json").read_text())
    names = {item["name"] for item in config["packages"]}
    assert names & FIREBASE == (FIREBASE if play else set()), f"{package.name}: Firebase channel isolation failed"
    if artifact:
        with zipfile.ZipFile(artifact) as archive:
            dex = b"".join(archive.read(n) for n in archive.namelist() if n.endswith(".dex"))
            assert dex, "APK/AAB has no DEX files"
            for symbol in (b"com/google/firebase/analytics", b"com/google/firebase/crashlytics"):
                assert (symbol in dex) == play, f"{package.name}: unexpected Firebase bytecode {symbol!r}"
    print(f"{package.name}: Firebase {'enabled' if play else 'absent'}; isolation passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package", help="App directory, relative to app/, e.g. app_student_googleplay")
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    check(ROOT / "app" / args.package, args.artifact)
