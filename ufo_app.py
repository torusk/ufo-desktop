#!/usr/bin/env python3
"""UFO Desktop App - Phase 1: Floating UFO display for macOS"""

import math
import os
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

# --- Animation constants ---
UFO_SIZE = 120
VERTICAL_AMPLITUDE = 12.0    # px up/down
HORIZONTAL_AMPLITUDE = 4.0   # px left/right
ANIMATION_PERIOD = 3.0       # seconds per full vertical cycle
TIMER_INTERVAL = 1.0 / 60.0  # 60 fps


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        # Background app: no dock icon, but still functional
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._setup_window()
        self._setup_status_item()
        self._start_animation()

    def _setup_window(self):
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        screen_w = sf.size.width
        screen_h = sf.size.height

        # Default position: bottom-right, above Dock
        self._base_x = screen_w - UFO_SIZE - 40.0
        self._base_y = 80.0

        rect = CGRectMake(self._base_x, self._base_y, UFO_SIZE, UFO_SIZE)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(25)  # NSStatusWindowLevel
        self._window.setIgnoresMouseEvents_(True)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(False)

        # Load and display UFO image
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        image_path = os.path.join(assets_dir, "UFO.png")
        ufo_image = NSImage.alloc().initWithContentsOfFile_(image_path)

        image_view = NSImageView.alloc().initWithFrame_(
            CGRectMake(0, 0, UFO_SIZE, UFO_SIZE)
        )
        image_view.setImage_(ufo_image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        image_view.setWantsLayer_(True)

        self._window.contentView().addSubview_(image_view)
        self._window.orderFrontRegardless()

    def _setup_status_item(self):
        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(-1)
        self._status_item.button().setTitle_("🛸")

        menu = NSMenu.alloc().init()

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "terminate:", "q"
        )
        menu.addItem_(quit_item)
        self._status_item.setMenu_(menu)

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

        # Sine-wave floating: vertical uses base period, horizontal uses a slightly
        # different period to create a natural Lissajous-like drift
        dy = VERTICAL_AMPLITUDE * math.sin(2.0 * math.pi * t / ANIMATION_PERIOD)
        dx = HORIZONTAL_AMPLITUDE * math.sin(2.0 * math.pi * t / (ANIMATION_PERIOD * 1.7))

        new_x = self._base_x + dx
        new_y = self._base_y + dy

        self._window.setFrameOrigin_(CGPointMake(new_x, new_y))


def main():
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
