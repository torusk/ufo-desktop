"""
autostart.py — macOS Launch Agent による自動起動管理

ログイン時に UFO アプリを自動起動するための
launchd plist を生成・登録・解除する関数群。
"""

import os
import shutil
import subprocess

# Launch Agent の識別子と plist のパス
LABEL = "com.ufo.desktop"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")

# 起動対象スクリプト（このファイルと同じディレクトリの ufo_app.py）
_APP_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "ufo_app.py"))


def is_enabled():
    """plist が存在すれば自動起動が有効と判断する。"""
    return os.path.exists(PLIST_PATH)


def enable():
    """
    Launch Agent を登録してログイン時自動起動を有効にする。
    uv のパスを自動検出（見つからなければ /opt/homebrew/bin/uv にフォールバック）。
    """
    uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv}</string>
        <string>run</string>
        <string>python</string>
        <string>{_APP_SCRIPT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>"""
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
    with open(PLIST_PATH, "w") as f:
        f.write(plist_content)
    subprocess.run(["launchctl", "load", PLIST_PATH], check=False)


def disable():
    """Launch Agent を解除してログイン時自動起動を無効にする。"""
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH], check=False)
        os.remove(PLIST_PATH)
