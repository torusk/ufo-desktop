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
from Quartz import CGPointMake, CGRectMake


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
    UFO 画像の上に重ねる透明なイベント受け取りビュー。

    操作とアクション:
      シングルクリック → 0.3秒タイマーで待機 → toggleAnimation()（浮遊トグル）
      ダブルクリック   → タイマーをキャンセル → screencapture -i -s（矩形選択スクショ）
      右クリック       → メニューバーと同じメニューをコンテキストメニューとして表示
      停止中ドラッグ   → UFO ウィンドウを移動（浮遊中は移動不可）

    シングル/ダブルの判定:
      mouseDown_ でシングル用 NSTimer を仕掛け、0.3秒以内に 2 回目が来たら
      タイマーをキャンセルしてダブルクリック処理を実行する。
    """

    # クラス変数（全インスタンス共有）
    _last_screenshot = 0.0  # 連続スクショ防止用タイムスタンプ（2秒以内の連打を無視）
    _pending_timer = None   # シングルクリック用の待機タイマー

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


class ResizeHandleView(NSView):
    """
    メッセージパネルの左下コーナーに配置するリサイズハンドル。

    ドラッグすると右上コーナーを固定したままウィンドウを拡縮する。
    ドラッグ量に応じて AppDelegate.resize_msg_panel() を呼び出し、
    サブビューの frame とフォントサイズを再計算させる。

    座標計算:
      マウス開始位置と現在位置の差分 (dx, dy) を使って
      「右上 = 固定」の制約でウィンドウの新しい origin とサイズを求める:
        new_w = max(220, 右上x - (元左端x + dx))
        new_h = max(200, 右上y - (元下端y + dy))
        new_x = 右上x - new_w
        new_y = 右上y - new_h
    """

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        sl = NSEvent.mouseLocation()
        self._sx = sl.x
        self._sy = sl.y
        f = self.window().frame()
        self._wox = f.origin.x
        self._woy = f.origin.y
        self._ww  = f.size.width
        self._wh  = f.size.height

    def mouseDragged_(self, event):
        sl = NSEvent.mouseLocation()
        dx = sl.x - self._sx
        dy = sl.y - self._sy
        tr_x = self._wox + self._ww   # 右上を固定
        tr_y = self._woy + self._wh
        new_w = max(220, tr_x - (self._wox + dx))
        new_h = max(200, tr_y - (self._woy + dy))
        new_x = tr_x - new_w
        new_y = tr_y - new_h
        self.window().setFrame_display_(CGRectMake(new_x, new_y, new_w, new_h), True)
        NSApp.delegate().resize_msg_panel(new_w, new_h)
