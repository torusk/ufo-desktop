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
    launchd の環境では uv run が動かないため、.venv の Python を直接使用する。
    """
    _app_dir = os.path.dirname(_APP_SCRIPT)
    python = os.path.join(_app_dir, ".venv", "bin", "python3")
    log_dir = os.path.expanduser("~/Library/Logs")
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{_APP_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{_app_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>{log_dir}/ufo_desktop.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/ufo_desktop_err.log</string>
</dict>
</plist>"""
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
    with open(PLIST_PATH, "w") as f:
        f.write(plist_content)
    subprocess.run(["launchctl", "unload", PLIST_PATH], check=False)
    subprocess.run(["launchctl", "load", PLIST_PATH], check=False)


def disable():
    """Launch Agent を解除してログイン時自動起動を無効にする。"""
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH], check=False)
        os.remove(PLIST_PATH)


# ---------------------------------------------------------------------------
# ブリーフィング自動実行（毎朝指定時刻）
# ---------------------------------------------------------------------------

_BRIEFING_LABEL  = "com.ufo.briefing"
_BRIEFING_PLIST  = os.path.expanduser(f"~/Library/LaunchAgents/{_BRIEFING_LABEL}.plist")
_BRIEFING_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "briefing.py"))
_BRIEFING_LOG    = os.path.abspath(os.path.join(os.path.dirname(__file__), "briefings", "auto.log"))


def briefing_is_enabled() -> bool:
    return os.path.exists(_BRIEFING_PLIST)


def briefing_enable(hour: int = 7, minute: int = 0):
    """
    毎朝 hour:minute に briefing.py を実行する Launch Agent を登録する。
    スリープ中に時刻を過ぎた場合は、次回起動時に自動実行される。
    """
    _app_dir = os.path.dirname(_BRIEFING_SCRIPT)
    python   = os.path.join(_app_dir, ".venv", "bin", "python3")
    os.makedirs(os.path.dirname(_BRIEFING_PLIST), exist_ok=True)
    os.makedirs(os.path.dirname(_BRIEFING_LOG), exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_BRIEFING_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{_BRIEFING_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{_app_dir}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{_BRIEFING_LOG}</string>
    <key>StandardErrorPath</key>
    <string>{_BRIEFING_LOG}</string>
</dict>
</plist>"""
    with open(_BRIEFING_PLIST, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "unload", _BRIEFING_PLIST], check=False)
    subprocess.run(["launchctl", "load",   _BRIEFING_PLIST], check=False)


def briefing_disable():
    if os.path.exists(_BRIEFING_PLIST):
        subprocess.run(["launchctl", "unload", _BRIEFING_PLIST], check=False)
        os.remove(_BRIEFING_PLIST)
