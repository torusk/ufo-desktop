#!/usr/bin/env python3
"""UFO Desktop App - Floating UFO with nanobot gateway control"""

import math
import os
import random
import signal
import subprocess
import time

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSScreen,
    NSStatusBar,
    NSTimer,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Quartz import CGPointMake, CGRectMake

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

# --- Nanobot ---
# nanobotプロジェクトのパス（自分の環境に合わせて変更）
NANOBOT_DIR = os.path.expanduser("~/Desktop/nanobot")


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._nanobot_proc = None

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
        x_min = MARGIN
        x_max = w - UFO_SIZE - MARGIN
        y_min = MARGIN + 20
        y_max = h - UFO_SIZE - 40
        return x_min, x_max, y_min, y_max

    def _random_waypoint(self):
        x_min, x_max, y_min, y_max = self._screen_bounds()
        return random.uniform(x_min, x_max), random.uniform(y_min, y_max)

    # ------------------------------------------------------------------
    def _setup_window(self):
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        start_x = (sf.size.width  - UFO_SIZE) / 2
        start_y = (sf.size.height - UFO_SIZE) / 2

        self._pos_x = start_x
        self._pos_y = start_y
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
        self._window.setLevel_(25)
        self._window.setIgnoresMouseEvents_(True)
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

        self._window.contentView().addSubview_(image_view)
        self._window.orderFrontRegardless()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _setup_status_item(self):
        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(-1)
        self._update_menu_bar_icon()

        menu = NSMenu.alloc().init()

        # nanobot 起動/停止
        self._nanobot_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "nanobot 起動", "toggleNanobot:", "n"
        )
        self._nanobot_item.setTarget_(self)
        menu.addItem_(self._nanobot_item)

        # セパレータ
        menu.addItem_(NSMenuItem.separatorItem())

        # 終了
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)

    def _update_menu_bar_icon(self):
        running = self._is_nanobot_running()
        # 起動中: 🛸  停止中: 🛸💤
        self._status_item.button().setTitle_("🛸" if running else "🛸💤")

    def _is_nanobot_running(self):
        if self._nanobot_proc is None:
            return False
        return self._nanobot_proc.poll() is None

    # ------------------------------------------------------------------
    # Nanobot gateway control
    # ------------------------------------------------------------------
    @objc.typedSelector(b"v@:@")
    def toggleNanobot_(self, sender):
        if self._is_nanobot_running():
            self._stop_nanobot()
        else:
            self._start_nanobot()

    def _start_nanobot(self):
        if self._is_nanobot_running():
            return
        try:
            self._nanobot_proc = subprocess.Popen(
                ["uv", "run", "nanobot", "gateway"],
                cwd=NANOBOT_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError:
            # uv が見つからない場合、venv 経由でフォールバック
            venv_bin = os.path.join(NANOBOT_DIR, ".venv", "bin", "nanobot")
            self._nanobot_proc = subprocess.Popen(
                [venv_bin, "gateway"],
                cwd=NANOBOT_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
        self._nanobot_item.setTitle_("nanobot 停止")
        self._update_menu_bar_icon()

    def _stop_nanobot(self):
        if not self._is_nanobot_running():
            return
        # プロセスグループごと終了（子プロセスも含めて）
        os.killpg(os.getpgid(self._nanobot_proc.pid), signal.SIGTERM)
        try:
            self._nanobot_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self._nanobot_proc.pid), signal.SIGKILL)
        self._nanobot_proc = None
        self._nanobot_item.setTitle_("nanobot 起動")
        self._update_menu_bar_icon()

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        self._stop_nanobot()
        NSApp.terminate_(None)

    def applicationWillTerminate_(self, notification):
        self._stop_nanobot()

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------
    def _start_animation(self):
        self._start_time = time.monotonic()
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            TIMER_INTERVAL,
            self,
            "animationTick:",
            None,
            True,
        )

    @objc.typedSelector(b"v@:@")
    def animationTick_(self, timer):
        t = time.monotonic() - self._start_time

        dx = self._target_x - self._pos_x
        dy = self._target_y - self._pos_y
        dist = math.hypot(dx, dy)

        if dist < ARRIVE_THRESHOLD:
            self._target_x, self._target_y = self._random_waypoint()
        else:
            self._pos_x += (dx / dist) * ROAM_SPEED
            self._pos_y += (dy / dist) * ROAM_SPEED

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
