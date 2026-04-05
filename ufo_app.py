#!/usr/bin/env python3
"""UFO Desktop App - Phase 1: Floating UFO roaming the entire desktop"""

import datetime
import math
import os
import random
import subprocess
import time

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSScreen,
    NSStatusBar,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Quartz import CGPointMake, CGRectMake


class ClickableView(NSView):
    """透明なクリック受け取りビュー。
    シングルクリック → スクショ起動
    ダブルクリック  → 浮遊トグル（停止 ↔ 再開）
    """

    _last_screenshot = 0.0  # スクショの連続発火防止
    _pending_timer = None   # シングルクリック判定用遅延タイマー

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        self._dragged = False
        # ドラッグ用にクリック位置（ウィンドウ内座標）を保存
        loc = event.locationInWindow()
        self._drag_offset_x = loc.x
        self._drag_offset_y = loc.y

        if event.clickCount() == 2:
            # ダブルクリック: 保留中のトグルをキャンセルしてスクショ
            if ClickableView._pending_timer is not None:
                ClickableView._pending_timer.invalidate()
                ClickableView._pending_timer = None
            now = time.monotonic()
            if now - ClickableView._last_screenshot < 2.0:
                return
            ClickableView._last_screenshot = now
            capture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ufocapture")
            os.makedirs(capture_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d at %H.%M.%S")
            save_path = os.path.join(capture_dir, f"Screenshot {timestamp}.png")
            subprocess.Popen(["screencapture", "-i", "-s", save_path])
            return

        # シングルクリック: 300ms待ってダブルクリック/ドラッグでなければ浮遊トグル
        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "fireToggle:", None, False
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
        ClickableView._pending_timer = t

    def mouseDragged_(self, event):
        delegate = NSApp.delegate()
        if delegate._ufo_visible:  # アニメーション中はドラッグしない
            return

        # ドラッグ開始: スクショタイマーをキャンセル
        if not self._dragged:
            self._dragged = True
            if ClickableView._pending_timer is not None:
                ClickableView._pending_timer.invalidate()
                ClickableView._pending_timer = None

        # スクリーン座標でマウス位置を取得して窓を移動
        screen_loc = NSEvent.mouseLocation()
        new_x = screen_loc.x - self._drag_offset_x
        new_y = screen_loc.y - self._drag_offset_y
        self.window().setFrameOrigin_(CGPointMake(new_x, new_y))

    def mouseUp_(self, event):
        if self._dragged:
            # ドロップ位置をデリゲートに反映（再開時にここから動き出す）
            origin = self.window().frame().origin
            delegate = NSApp.delegate()
            delegate._pos_x = origin.x
            delegate._pos_y = origin.y
            self._dragged = False

    @objc.typedSelector(b"v@:@")
    def fireToggle_(self, timer):
        ClickableView._pending_timer = None
        NSApp.delegate().toggleAnimation()

# --- Display ---
UFO_SIZE = 120

# --- Roaming ---
ROAM_SPEED = 1.8          # px per frame (≈108 px/s at 60fps)
ARRIVE_THRESHOLD = 60.0   # px — how close before picking next waypoint
MARGIN = 60               # keep UFO this far from screen edges

# --- Floating wobble on top of roaming ---
WOBBLE_Y_AMP = 8.0        # px vertical wobble amplitude
WOBBLE_X_AMP = 3.0        # px horizontal wobble amplitude
WOBBLE_PERIOD = 2.8       # seconds

TIMER_INTERVAL = 1.0 / 60.0


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._setup_window()
        self._setup_status_item()
        self._start_animation()

    # ------------------------------------------------------------------
    def _screen_bounds(self):
        """Usable roaming area (Cocoa coords, origin = bottom-left)."""
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        w = sf.size.width
        h = sf.size.height
        # Keep away from Dock (bottom) and menu bar (top)
        x_min = MARGIN
        x_max = w - UFO_SIZE - MARGIN
        y_min = MARGIN + 20        # a bit above Dock
        y_max = h - UFO_SIZE - 40  # below menu bar
        return x_min, x_max, y_min, y_max

    def _random_waypoint(self):
        x_min, x_max, y_min, y_max = self._screen_bounds()
        return random.uniform(x_min, x_max), random.uniform(y_min, y_max)

    # ------------------------------------------------------------------
    def _setup_window(self):
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        # Start at centre of screen
        start_x = (sf.size.width  - UFO_SIZE) / 2
        start_y = (sf.size.height - UFO_SIZE) / 2

        # Current smooth position (float, updated every frame)
        self._pos_x = start_x
        self._pos_y = start_y

        # First waypoint
        self._target_x, self._target_y = self._random_waypoint()

        rect = CGRectMake(start_x, start_y, UFO_SIZE, UFO_SIZE)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(25)  # NSStatusWindowLevel
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(False)

        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        ufo_image = NSImage.alloc().initWithContentsOfFile_(
            os.path.join(assets_dir, "UFO.png")
        )
        image_view = NSImageView.alloc().initWithFrame_(
            CGRectMake(0, 0, UFO_SIZE, UFO_SIZE)
        )
        image_view.setImage_(ufo_image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        image_view.setWantsLayer_(True)

        # クリック受け取り用の透明ビューをUFOの上に重ねる
        click_view = ClickableView.alloc().initWithFrame_(
            CGRectMake(0, 0, UFO_SIZE, UFO_SIZE)
        )

        self._window.contentView().addSubview_(image_view)
        self._window.contentView().addSubview_(click_view)
        self._window.orderFrontRegardless()

    def _setup_status_item(self):
        self._ufo_visible = True

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(-1)
        self._status_item.button().setTitle_("🛸")

        menu = NSMenu.alloc().init()

        self._toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "UFO 停止", "toggleUFO:", "u"
        )
        self._toggle_item.setTarget_(self)
        menu.addItem_(self._toggle_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)

    @objc.typedSelector(b"v@:@")
    def toggleUFO_(self, sender):
        self.toggleAnimation()

    def toggleAnimation(self):
        if self._ufo_visible:
            self._timer.invalidate()
            self._ufo_visible = False
            self._toggle_item.setTitle_("UFO 起動")
            self._status_item.button().setTitle_("🛸💤")
        else:
            self._start_animation()
            self._ufo_visible = True
            self._toggle_item.setTitle_("UFO 停止")
            self._status_item.button().setTitle_("🛸")

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        NSApp.terminate_(None)

    # ------------------------------------------------------------------
    def _start_animation(self):
        self._start_time = time.monotonic()
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            TIMER_INTERVAL, self, "animationTick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    @objc.typedSelector(b"v@:@")
    def animationTick_(self, timer):
        t = time.monotonic() - self._start_time

        # --- Roaming: move toward current waypoint at fixed speed ---
        dx = self._target_x - self._pos_x
        dy = self._target_y - self._pos_y
        dist = math.hypot(dx, dy)

        if dist < ARRIVE_THRESHOLD:
            # Reached waypoint — pick the next one
            self._target_x, self._target_y = self._random_waypoint()
        else:
            # Normalise direction and advance
            self._pos_x += (dx / dist) * ROAM_SPEED
            self._pos_y += (dy / dist) * ROAM_SPEED

        # --- Wobble: gentle sine-wave layered on top of roaming ---
        wobble_y = WOBBLE_Y_AMP * math.sin(2.0 * math.pi * t / WOBBLE_PERIOD)
        wobble_x = WOBBLE_X_AMP * math.sin(2.0 * math.pi * t / (WOBBLE_PERIOD * 1.6))

        self._window.setFrameOrigin_(
            CGPointMake(self._pos_x + wobble_x, self._pos_y + wobble_y)
        )


def main():
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
