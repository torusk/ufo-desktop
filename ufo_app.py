#!/usr/bin/env python3
"""
ufo_app.py — エントリーポイント

アプリの起動処理のみを行う。
機能の実装は各モジュールに分離されている:
  views.py     — カスタム NSView / NSWindow クラス
  telegram.py  — Telegram 送受信・ポーリング
  autostart.py — ログイン時自動起動 (Launch Agent)
  delegate.py  — AppDelegate（全体の司令塔）
"""

from AppKit import NSApplication
from delegate import AppDelegate


def main():
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
