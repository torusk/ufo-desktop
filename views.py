"""
views.py — カスタム NSView / NSWindow サブクラス群

UFO アプリ固有の UI コンポーネントをここにまとめる。
AppDelegate から参照されるだけで、逆方向の依存はない。
"""

import datetime
import os
import subprocess
import time

import objc
from AppKit import (
    NSApp,
    NSEvent,
    NSMenu,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
    NSView,
    NSWindow,
)
from Quartz import CGPointMake


class KeyableWindow(NSWindow):
    """
    ボーダレスウィンドウでもキーボード入力を受け付けるサブクラス。
    メッセージ入力パネルに使用する。
    """

    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class LogPanelView(NSView):
    """
    ログパネルのドラッグ操作を受け付けるビュー。
    マウスドラッグでパネルウィンドウ全体を移動できる。
    """

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        loc = event.locationInWindow()
        self._ox = loc.x
        self._oy = loc.y

    def mouseDragged_(self, event):
        sl = NSEvent.mouseLocation()
        self.window().setFrameOrigin_(CGPointMake(sl.x - self._ox, sl.y - self._oy))


class ClickableView(NSView):
    """
    UFO 画像の上に重ねるイベント受け取りビュー。

    シングルクリック → アニメーション浮遊トグル（0.3秒待機でダブルと区別）
    ダブルクリック   → スクリーンショット撮影（screencapture -i -s）
    右クリック       → コンテキストメニュー表示
    停止中ドラッグ   → UFO とメッセージパネルを移動
    """

    # クラス変数（全インスタンス共有）
    _last_screenshot = 0.0  # 連続スクショ防止用タイムスタンプ
    _pending_timer = None   # シングル/ダブルクリック判定タイマー

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        self._dragged = False
        loc = event.locationInWindow()
        self._drag_offset_x = loc.x
        self._drag_offset_y = loc.y

        if event.clickCount() == 2:
            # ダブルクリック: 待機タイマーをキャンセルしてスクショ起動
            if ClickableView._pending_timer is not None:
                ClickableView._pending_timer.invalidate()
                ClickableView._pending_timer = None
            now = time.monotonic()
            if now - ClickableView._last_screenshot < 2.0:
                return  # 2秒以内の連打は無視
            ClickableView._last_screenshot = now
            capture_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ufocapture"
            )
            os.makedirs(capture_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y-%m-%d at %H.%M.%S")
            subprocess.Popen(
                ["screencapture", "-i", "-s", os.path.join(capture_dir, f"Screenshot {ts}.png")]
            )
            return

        # シングルクリック: 0.3秒後に発火（ダブルなら上でキャンセルされる）
        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "fireToggle:", None, False
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
        ClickableView._pending_timer = t

    def mouseDragged_(self, event):
        delegate = NSApp.delegate()
        if delegate._ufo_visible:
            return  # 浮遊中はドラッグ移動不可
        if not self._dragged:
            self._dragged = True
            # ドラッグ開始: シングルクリックタイマーをキャンセル
            if ClickableView._pending_timer is not None:
                ClickableView._pending_timer.invalidate()
                ClickableView._pending_timer = None
        screen_loc = NSEvent.mouseLocation()
        new_x = screen_loc.x - self._drag_offset_x
        new_y = screen_loc.y - self._drag_offset_y
        self.window().setFrameOrigin_(CGPointMake(new_x, new_y))
        delegate._update_msg_panel_position()  # メッセージパネルも同期移動

    def mouseUp_(self, event):
        if self._dragged:
            # ドラッグ終了: 座標をアニメーション基準位置として保存
            origin = self.window().frame().origin
            delegate = NSApp.delegate()
            delegate._pos_x = origin.x
            delegate._pos_y = origin.y
            self._dragged = False

    def rightMouseDown_(self, event):
        # メニューバーと同じメニューをコンテキストメニューとして表示
        menu = NSApp.delegate()._status_item.menu()
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    @objc.typedSelector(b"v@:@")
    def fireToggle_(self, timer):
        ClickableView._pending_timer = None
        NSApp.delegate().toggleAnimation()
