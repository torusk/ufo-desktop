#!/usr/bin/env python3
"""UFO Desktop App - Floating UFO with nanobot gateway control"""

import collections
import datetime
import json
import math
import os
import random
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSAttributedString,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSScreen,
    NSScrollView,
    NSStatusBar,
    NSTextField,
    NSTextView,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Quartz import CGPointMake, CGRectMake

# --- Nanobot ---
NANOBOT_DIR = os.path.expanduser("~/Desktop/nanobot")

# --- Telegram ---
TELEGRAM_CONFIG_PATH = os.path.expanduser("~/.ufo_config.json")

# --- Message panel ---
MSG_PANEL_W = 230
MSG_PANEL_H = 42

# --- Display ---
UFO_SIZE = 120

# --- Roaming ---
ROAM_SPEED = 1.8
ARRIVE_THRESHOLD = 60.0
MARGIN = 60

# --- Floating wobble ---
WOBBLE_Y_AMP = 8.0
WOBBLE_X_AMP = 3.0
WOBBLE_PERIOD = 2.8

TIMER_INTERVAL = 1.0 / 60.0

# --- Log panel ---
PANEL_W = 460
PANEL_H = 220
PANEL_PADDING = 10
LOG_MAX_LINES = 150


class ClickableView(NSView):
    """UFOクリック受け取りビュー。
    シングルクリック → 浮遊トグル
    ダブルクリック  → スクショ
    停止中ドラッグ  → 移動
    """

    _last_screenshot = 0.0
    _pending_timer = None

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        self._dragged = False
        loc = event.locationInWindow()
        self._drag_offset_x = loc.x
        self._drag_offset_y = loc.y

        if event.clickCount() == 2:
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

        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "fireToggle:", None, False
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
        ClickableView._pending_timer = t

    def mouseDragged_(self, event):
        delegate = NSApp.delegate()
        if delegate._ufo_visible:
            return
        if not self._dragged:
            self._dragged = True
            if ClickableView._pending_timer is not None:
                ClickableView._pending_timer.invalidate()
                ClickableView._pending_timer = None
        screen_loc = NSEvent.mouseLocation()
        new_x = screen_loc.x - self._drag_offset_x
        new_y = screen_loc.y - self._drag_offset_y
        self.window().setFrameOrigin_(CGPointMake(new_x, new_y))

    def mouseUp_(self, event):
        if self._dragged:
            origin = self.window().frame().origin
            delegate = NSApp.delegate()
            delegate._pos_x = origin.x
            delegate._pos_y = origin.y
            self._dragged = False

    def rightMouseDown_(self, event):
        menu = NSApp.delegate()._status_item.menu()
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    @objc.typedSelector(b"v@:@")
    def fireToggle_(self, timer):
        ClickableView._pending_timer = None
        NSApp.delegate().toggleAnimation()


class KeyableWindow(NSWindow):
    """キーボード入力を受け付けるボーダレスウィンドウ。"""

    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class LogPanelView(NSView):
    """ログパネルのドラッグ用ビュー。"""

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        loc = event.locationInWindow()
        self._ox = loc.x
        self._oy = loc.y

    def mouseDragged_(self, event):
        sl = NSEvent.mouseLocation()
        self.window().setFrameOrigin_(CGPointMake(sl.x - self._ox, sl.y - self._oy))


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._nanobot_proc = None
        self._log_lines = []
        self._log_queue = collections.deque()

        self._setup_window()
        self._setup_log_panel()
        self._setup_message_panel()
        self._setup_status_item()
        self._start_animation()

        # ログキュー drain タイマー
        drain_timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.25, self, "drainLogQueue:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(drain_timer, NSRunLoopCommonModes)

    # ------------------------------------------------------------------
    def _screen_bounds(self):
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
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(False)

        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        ufo_image = NSImage.alloc().initWithContentsOfFile_(
            os.path.join(assets_dir, "UFO.png")
        )
        image_view = NSImageView.alloc().initWithFrame_(CGRectMake(0, 0, UFO_SIZE, UFO_SIZE))
        image_view.setImage_(ufo_image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        image_view.setWantsLayer_(True)

        click_view = ClickableView.alloc().initWithFrame_(CGRectMake(0, 0, UFO_SIZE, UFO_SIZE))

        self._window.contentView().addSubview_(image_view)
        self._window.contentView().addSubview_(click_view)
        self._window.orderFrontRegardless()

    # ------------------------------------------------------------------
    # Log panel
    # ------------------------------------------------------------------
    def _setup_log_panel(self):
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        # 初期位置: 左下
        px = 20
        py = 60

        self._log_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(px, py, PANEL_W, PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._log_window.setOpaque_(False)
        self._log_window.setBackgroundColor_(NSColor.clearColor())
        self._log_window.setLevel_(24)  # UFO (25) の一段下
        self._log_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._log_window.setHasShadow_(False)

        # ドラッグ可能な背景ビュー（角丸・半透明ダーク）
        bg = LogPanelView.alloc().initWithFrame_(CGRectMake(0, 0, PANEL_W, PANEL_H))
        bg.setWantsLayer_(True)
        dark = NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.05, 0.05, 0.88)
        bg.layer().setBackgroundColor_(dark.CGColor())
        bg.layer().setCornerRadius_(12.0)

        # スクロールビュー
        p = PANEL_PADDING
        inner_w = PANEL_W - p * 2
        inner_h = PANEL_H - p * 2
        scroll = NSScrollView.alloc().initWithFrame_(CGRectMake(p, p, inner_w, inner_h))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)

        # テキストビュー
        self._log_text = NSTextView.alloc().initWithFrame_(CGRectMake(0, 0, inner_w, inner_h))
        self._log_text.setEditable_(False)
        self._log_text.setSelectable_(True)
        self._log_text.setDrawsBackground_(False)
        self._log_text.setVerticallyResizable_(True)
        self._log_text.setHorizontallyResizable_(False)
        self._log_text.textContainer().setWidthTracksTextView_(True)
        self._log_text.setMinSize_((inner_w, inner_h))
        self._log_text.setMaxSize_((inner_w, 1e8))

        scroll.setDocumentView_(self._log_text)
        bg.addSubview_(scroll)
        self._log_window.contentView().addSubview_(bg)
        # 起動時は非表示

    # ------------------------------------------------------------------
    # Message panel (Telegram送信)
    # ------------------------------------------------------------------
    def _setup_message_panel(self):
        self._msg_panel_visible = False

        self._msg_window = KeyableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(0, 0, MSG_PANEL_W, MSG_PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._msg_window.setOpaque_(False)
        self._msg_window.setBackgroundColor_(NSColor.clearColor())
        self._msg_window.setLevel_(25)
        self._msg_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._msg_window.setHasShadow_(False)

        bg = NSView.alloc().initWithFrame_(CGRectMake(0, 0, MSG_PANEL_W, MSG_PANEL_H))
        bg.setWantsLayer_(True)
        light = NSColor.colorWithSRGBRed_green_blue_alpha_(0.88, 0.88, 0.88, 0.55)
        bg.layer().setBackgroundColor_(light.CGColor())
        bg.layer().setCornerRadius_(10.0)

        p = 7
        field_h = MSG_PANEL_H - p * 2
        self._msg_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(p, p, MSG_PANEL_W - p * 2, field_h)
        )
        self._msg_field.setPlaceholderString_("Telegramへ送信... (Enter)")
        self._msg_field.setBezeled_(False)
        self._msg_field.setDrawsBackground_(False)
        self._msg_field.setTextColor_(NSColor.darkGrayColor())
        self._msg_field.setFont_(NSFont.systemFontOfSize_(12))
        self._msg_field.setAction_("sendTelegramMessage:")
        self._msg_field.setTarget_(self)

        bg.addSubview_(self._msg_field)
        self._msg_window.contentView().addSubview_(bg)

    def _update_msg_panel_position(self):
        if not self._msg_panel_visible:
            return
        frame = self._window.frame()
        mx = frame.origin.x + (UFO_SIZE - MSG_PANEL_W) / 2
        my = frame.origin.y - MSG_PANEL_H - 5
        self._msg_window.setFrameOrigin_(CGPointMake(mx, my))

    def _show_msg_panel(self):
        self._msg_panel_visible = True  # 先にセットしないと位置更新がスキップされる
        self._update_msg_panel_position()
        self._msg_window.orderFrontRegardless()
        self._msg_panel_item.setTitle_("メッセージ欄を非表示")

    def _hide_msg_panel(self):
        self._msg_window.orderOut_(None)
        self._msg_panel_visible = False
        self._msg_panel_item.setTitle_("メッセージ欄を表示")

    @objc.typedSelector(b"v@:@")
    def toggleMsgPanel_(self, sender):
        if self._msg_panel_visible:
            self._hide_msg_panel()
        else:
            self._show_msg_panel()

    @objc.typedSelector(b"v@:@")
    def sendTelegramMessage_(self, sender):
        text = self._msg_field.stringValue().strip()
        if not text:
            return
        config = self._load_telegram_config()
        if not config:
            self._log_queue.append(
                "[Telegram] 未設定: ~/.ufo_config.json に telegram_token と telegram_chat_id を設定してください"
            )
            self._show_log_panel()
            return
        token = config.get("telegram_token", "")
        chat_id = str(config.get("telegram_chat_id", ""))
        if not token or not chat_id:
            self._log_queue.append("[Telegram] telegram_token または telegram_chat_id が未設定です")
            self._show_log_panel()
            return
        self._msg_field.setStringValue_("")
        threading.Thread(
            target=self._send_telegram,
            args=(token, chat_id, text),
            daemon=True,
        ).start()

    def _send_telegram(self, token, chat_id, text):
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            self._log_queue.append(f"[Telegram] 送信完了: {text[:60]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            self._log_queue.append(f"[Telegram] HTTPエラー {e.code}: {body[:120]}")
        except Exception as e:
            self._log_queue.append(f"[Telegram] 送信エラー: {e}")

    def _load_telegram_config(self):
        # 1. 環境変数
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            return {"telegram_token": token, "telegram_chat_id": chat_id}

        # 2. ~/.ufo_config.json (独自設定)
        try:
            with open(TELEGRAM_CONFIG_PATH) as f:
                cfg = json.load(f)
            if cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
                return cfg
        except Exception:
            pass

        # 3. ~/.nanobot/config.json (nanobotの設定を流用)
        try:
            nanobot_cfg_path = os.path.expanduser("~/.nanobot/config.json")
            with open(nanobot_cfg_path) as f:
                nb = json.load(f)
            tg = nb.get("channels", {}).get("telegram", {})
            token = tg.get("token", "")
            allow_from = tg.get("allowFrom", [])
            chat_id = str(allow_from[0]) if allow_from else ""
            if token and chat_id:
                return {"telegram_token": token, "telegram_chat_id": chat_id}
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    @objc.typedSelector(b"v@:@")
    def drainLogQueue_(self, timer):
        if not self._log_queue:
            return
        changed = False
        while self._log_queue:
            try:
                line = self._log_queue.popleft()
                self._log_lines.append(line)
                if len(self._log_lines) > LOG_MAX_LINES:
                    self._log_lines.pop(0)
                changed = True
            except IndexError:
                break
        if changed:
            self._refresh_log_view()

    def _refresh_log_view(self):
        text = "\n".join(self._log_lines)
        font = NSFont.fontWithName_size_("Menlo", 10) or NSFont.monospacedSystemFontOfSize_weight_(10, 0)
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.2, 0.95, 0.45, 1.0)
        attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
        attr_str = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        self._log_text.textStorage().setAttributedString_(attr_str)
        end = len(text)
        self._log_text.scrollRangeToVisible_((end, 0))

    def _read_nanobot_output(self, proc):
        """バックグラウンドスレッド: nanobotのstdout/stderrを読んでキューに積む。"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._log_queue.append(line)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _setup_status_item(self):
        self._ufo_visible = True

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(-1)
        self._update_menu_bar_icon()

        menu = NSMenu.alloc().init()

        self._toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "UFO 停止", "toggleUFO:", "u"
        )
        self._toggle_item.setTarget_(self)
        menu.addItem_(self._toggle_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self._nanobot_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "nanobot 起動", "toggleNanobot:", "n"
        )
        self._nanobot_item.setTarget_(self)
        menu.addItem_(self._nanobot_item)

        self._log_panel_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ログを表示", "toggleLogPanel:", "l"
        )
        self._log_panel_item.setTarget_(self)
        menu.addItem_(self._log_panel_item)

        self._msg_panel_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "メッセージ欄を表示", "toggleMsgPanel:", "m"
        )
        self._msg_panel_item.setTarget_(self)
        menu.addItem_(self._msg_panel_item)

        telegram_info_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Telegram設定を確認...", "showTelegramStatus:", ""
        )
        telegram_info_item.setTarget_(self)
        menu.addItem_(telegram_info_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了", "quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)
        self._log_panel_visible = False

    def _update_menu_bar_icon(self):
        running = self._is_nanobot_running()
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
        # ログをクリアして表示
        self._log_lines.clear()
        self._log_queue.clear()
        self._refresh_log_view()
        self._show_log_panel()

        try:
            self._nanobot_proc = subprocess.Popen(
                ["uv", "run", "nanobot", "gateway"],
                cwd=NANOBOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError:
            venv_bin = os.path.join(NANOBOT_DIR, ".venv", "bin", "nanobot")
            self._nanobot_proc = subprocess.Popen(
                [venv_bin, "gateway"],
                cwd=NANOBOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )

        # stdout読み取りスレッド起動
        t = threading.Thread(
            target=self._read_nanobot_output,
            args=(self._nanobot_proc,),
            daemon=True,
        )
        t.start()

        self._nanobot_item.setTitle_("nanobot 停止")
        self._update_menu_bar_icon()

    def _stop_nanobot(self):
        if not self._is_nanobot_running():
            return
        os.killpg(os.getpgid(self._nanobot_proc.pid), signal.SIGTERM)
        try:
            self._nanobot_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self._nanobot_proc.pid), signal.SIGKILL)
        self._nanobot_proc = None
        self._nanobot_item.setTitle_("nanobot 起動")
        self._update_menu_bar_icon()

    # ------------------------------------------------------------------
    # Log panel visibility
    # ------------------------------------------------------------------
    def _show_log_panel(self):
        self._log_window.orderFrontRegardless()
        self._log_panel_visible = True
        self._log_panel_item.setTitle_("ログを非表示")

    def _hide_log_panel(self):
        self._log_window.orderOut_(None)
        self._log_panel_visible = False
        self._log_panel_item.setTitle_("ログを表示")

    @objc.typedSelector(b"v@:@")
    def toggleLogPanel_(self, sender):
        if self._log_panel_visible:
            self._hide_log_panel()
        else:
            self._show_log_panel()

    # ------------------------------------------------------------------
    @objc.typedSelector(b"v@:@")
    def showTelegramStatus_(self, sender):
        config = self._load_telegram_config()
        if config:
            token = config.get("telegram_token", "")
            chat_id = config.get("telegram_chat_id", "")
            masked = token[:8] + "..." if len(token) > 8 else "(未設定)"
            self._log_queue.append(f"[Telegram] token: {masked}  chat_id: {chat_id}")
        else:
            self._log_queue.append(
                "[Telegram] 設定なし — ~/.ufo_config.json を作成してください\n"
                '  例: {"telegram_token": "123:ABC...", "telegram_chat_id": "987654321"}'
            )
        self._show_log_panel()

    @objc.typedSelector(b"v@:@")
    def toggleUFO_(self, sender):
        self.toggleAnimation()

    def toggleAnimation(self):
        if self._ufo_visible:
            self._timer.invalidate()
            self._ufo_visible = False
            self._toggle_item.setTitle_("UFO 起動")
        else:
            self._start_animation()
            self._ufo_visible = True
            self._toggle_item.setTitle_("UFO 停止")
        self._update_menu_bar_icon()

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        self._stop_nanobot()
        NSApp.terminate_(None)

    def applicationWillTerminate_(self, notification):
        self._stop_nanobot()

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
        self._update_msg_panel_position()


def main():
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
