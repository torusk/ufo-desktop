"""
delegate.py — AppDelegate（アプリ全体の司令塔）

各機能モジュール（views / telegram / autostart）を組み合わせて
UFO アプリの動作を制御する。
"""

import base64
import collections
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
    NSMutableAttributedString,
    NSBackingStoreBuffered,
    NSBackgroundColorAttributeName,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSOpenPanel,
    NSPasteboard,
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
from Foundation import NSURL
from Quartz import CGPointMake, CGRectMake

import autostart
import icons
import telegram as tg
from views import ClickableView, KeyableWindow, LogPanelView

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# nanobot ゲートウェイのディレクトリ
NANOBOT_DIR = os.path.expanduser("~/Desktop/nanobot")

# UFO 画像サイズ（正方形）
UFO_SIZE = 120

# 自律移動パラメータ
ROAM_SPEED = 1.8         # 1フレームあたりの移動量(px)
ARRIVE_THRESHOLD = 60.0  # この距離以内に入ったら次のウェイポイントへ
MARGIN = 60              # 画面端からの最小距離(px)

# ふわふわアニメーションの振れ幅・周期
WOBBLE_Y_AMP = 8.0     # 縦方向の振れ幅(px)
WOBBLE_X_AMP = 3.0     # 横方向の振れ幅(px)
WOBBLE_PERIOD = 2.8    # 周期(秒)

# アニメーションタイマー間隔（30fps）
TIMER_INTERVAL = 1.0 / 30.0

# ログパネルのサイズ
LOG_PANEL_W = 460
LOG_PANEL_H = 220
LOG_PANEL_PADDING = 10
LOG_MAX_LINES = 150      # これを超えたら古い行を捨てる

# メッセージパネルのサイズ
MSG_PANEL_W = 230
MSG_PANEL_H = 170
MSG_CHAT_H = 118   # チャット表示エリア（上部）の高さ
MSG_INPUT_H = 28   # 入力フィールド（下部）の高さ

# OCR パネルのサイズ
OCR_PANEL_W = 300
OCR_PANEL_H = 270   # 翻訳ボタン行分を追加
OCR_PAD = 8
OCR_BTN_H = 28

# ショートカット登録パネルのサイズ
LAUNCHER_PANEL_W = 360
LAUNCHER_PANEL_H = 260
LAUNCHER_PAD = 8
LAUNCHER_ROW_H = 26

# 設定ファイルパス
CONFIG_PATH = os.path.expanduser("~/.ufo_config.json")


# ---------------------------------------------------------------------------
# AppDelegate
# ---------------------------------------------------------------------------

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, notification):
        # Dock に表示しないアクセサリアプリとして動作
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # --- 状態変数の初期化 ---
        self._nanobot_proc = None

        # ドット絵アイコンを生成・ロード
        icons.generate_all()
        self._load_menu_icons()

        # メニューバーアイコンのアニメーション用カウンター
        self._icon_tick = 0
        self._chat_flash_ticks = 0  # >0 の間チャットアイコンを表示

        # UFO 非表示フラグ
        self._ufo_hidden = False

        # ログパネル用: 行リスト + スレッド間受け渡しキュー
        self._log_lines = []
        self._log_queue = collections.deque()

        # チャットパネル用: メッセージリスト + スレッド間受け渡しキュー
        self._chat_messages = []        # list of ("sent" | "recv", text)
        self._chat_queue = collections.deque()

        # OCR パネル用: 結果キュー + 最終テキスト（コピー用）
        self._ocr_result_queue = collections.deque()  # (text, is_final) tuples
        self._ocr_final_text = ""
        self._ocr_original_text = ""  # 翻訳元として保持（再翻訳時に使用）

        # ショートカット登録パネル用
        self._launchers = self._load_launchers()
        self._launcher_dynamic_items = []

        # Telegram ポーラー（nanobot 停止中のみ動作）
        def _on_recv(text):
            self._chat_queue.append(("recv", text))
            self._chat_flash_ticks = 6  # 約3秒 💬🛸 を表示
        self._tg_poller = tg.TelegramPoller(on_message=_on_recv)

        # --- UI セットアップ ---
        self._setup_ufo_window()
        self._setup_log_panel()
        self._setup_message_panel()
        self._setup_ocr_panel()
        self._setup_launcher_panel()
        self._setup_menu_bar()
        self._start_animation()

        # ログキューを 0.25秒ごとにメインスレッドで処理
        self._add_timer("drainLogQueue:", 0.25, repeats=True)

        # チャットキューを 0.5秒ごとにメインスレッドで処理
        self._add_timer("drainChatQueue:", 0.5, repeats=True)

        # OCR 結果キューを 0.3秒ごとにメインスレッドで処理
        self._add_timer("drainOCRQueue:", 0.3, repeats=True)

        # Telegram ポーリング開始（nanobot が起動したら一時停止する）
        self._tg_poller.start()

    # -----------------------------------------------------------------------
    # ドット絵アイコン
    # -----------------------------------------------------------------------

    def _load_menu_icons(self):
        """assets/ のドット絵 PNG を NSImage としてロードする。"""
        def _load(name):
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", name
            )
            img = NSImage.alloc().initWithContentsOfFile_(path)
            img.setSize_((18, 18))
            img.setTemplate_(True)
            return img

        self._icon_idle     = _load("mb_idle.png")
        self._icon_active_a = _load("mb_active_a.png")
        self._icon_active_b = _load("mb_active_b.png")
        self._icon_chat     = _load("mb_chat.png")

    # -----------------------------------------------------------------------
    # ユーティリティ
    # -----------------------------------------------------------------------

    def _add_timer(self, selector, interval, repeats=True):
        """NSTimer を RunLoop に登録するヘルパー。"""
        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            interval, self, selector, None, repeats
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)

    def _screen_bounds(self):
        """UFO が移動できる画面内の矩形を (x_min, x_max, y_min, y_max) で返す。"""
        sf = NSScreen.mainScreen().frame()
        return (
            MARGIN,
            sf.size.width - UFO_SIZE - MARGIN,
            MARGIN + 20,
            sf.size.height - UFO_SIZE - 40,
        )

    def _random_waypoint(self):
        """ランダムなウェイポイント (x, y) を返す。"""
        x_min, x_max, y_min, y_max = self._screen_bounds()
        return random.uniform(x_min, x_max), random.uniform(y_min, y_max)

    # -----------------------------------------------------------------------
    # UFO ウィンドウ
    # -----------------------------------------------------------------------

    def _setup_ufo_window(self):
        """UFO 画像ウィンドウを生成して画面中央に配置する。"""
        sf = NSScreen.mainScreen().frame()
        start_x = (sf.size.width - UFO_SIZE) / 2
        start_y = (sf.size.height - UFO_SIZE) / 2

        # アニメーション用の論理座標（wobble オフセットを除いた基準位置）
        self._pos_x = start_x
        self._pos_y = start_y
        self._target_x, self._target_y = self._random_waypoint()

        # ボーダレス・透明・最前面ウィンドウ
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(start_x, start_y, UFO_SIZE, UFO_SIZE),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(25)  # 通常ウィンドウより前面
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(False)

        # UFO 画像
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

        # イベント受け取りビュー（画像の上に重ねる）
        click_view = ClickableView.alloc().initWithFrame_(
            CGRectMake(0, 0, UFO_SIZE, UFO_SIZE)
        )

        self._window.contentView().addSubview_(image_view)
        self._window.contentView().addSubview_(click_view)
        self._window.orderFrontRegardless()

    # -----------------------------------------------------------------------
    # アニメーション
    # -----------------------------------------------------------------------

    def _start_animation(self):
        """アニメーションタイマーを開始する。"""
        self._ufo_visible = True
        self._start_time = time.monotonic()
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            TIMER_INTERVAL, self, "animationTick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    @objc.typedSelector(b"v@:@")
    def animationTick_(self, timer):
        """60fps で呼ばれるアニメーションループ。移動 + wobble + パネル追従。"""
        t = time.monotonic() - self._start_time

        if not self._ufo_hidden:
            # ウェイポイントへ向かって直進
            dx = self._target_x - self._pos_x
            dy = self._target_y - self._pos_y
            dist = math.hypot(dx, dy)
            if dist < ARRIVE_THRESHOLD:
                self._target_x, self._target_y = self._random_waypoint()
            else:
                self._pos_x += (dx / dist) * ROAM_SPEED
                self._pos_y += (dy / dist) * ROAM_SPEED

            # サイン波でふわふわ揺らす
            wobble_y = WOBBLE_Y_AMP * math.sin(2.0 * math.pi * t / WOBBLE_PERIOD)
            wobble_x = WOBBLE_X_AMP * math.sin(2.0 * math.pi * t / (WOBBLE_PERIOD * 1.6))

            self._window.setFrameOrigin_(
                CGPointMake(self._pos_x + wobble_x, self._pos_y + wobble_y)
            )
            self._update_msg_panel_position()
            self._update_ocr_panel_position()
            self._update_launcher_panel_position()

        # メニューバーアイコンを 15tick（約0.5秒）ごとに更新
        self._icon_tick += 1
        if self._icon_tick % 15 == 0:
            if self._chat_flash_ticks > 0:
                self._chat_flash_ticks -= 1
            self._update_menu_bar_icon()

    def toggleAnimation(self):
        """アニメーション（浮遊）のオン/オフを切り替える。"""
        if self._ufo_visible:
            self._timer.invalidate()
            self._ufo_visible = False
            self._toggle_item.setTitle_("UFO 起動")
        else:
            self._start_animation()
            self._toggle_item.setTitle_("UFO 停止")
        self._update_menu_bar_icon()

    @objc.typedSelector(b"v@:@")
    def toggleUFO_(self, sender):
        self.toggleAnimation()

    @objc.typedSelector(b"v@:@")
    def toggleHide_(self, sender):
        """UFO ウィンドウの表示/非表示を切り替える。"""
        if self._ufo_hidden:
            self._window.orderFrontRegardless()
            self._ufo_hidden = False
            self._hide_item.setTitle_("UFO を隠す")
        else:
            self._window.orderOut_(None)
            self._ufo_hidden = True
            self._hide_item.setTitle_("UFO を表示")

    # -----------------------------------------------------------------------
    # ログパネル
    # -----------------------------------------------------------------------

    def _setup_log_panel(self):
        """
        nanobot の stdout を表示する半透明ダークパネルを生成する。
        初期位置は画面左下。起動時は非表示。
        """
        self._log_panel_visible = False

        self._log_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(20, 60, LOG_PANEL_W, LOG_PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._log_window.setOpaque_(False)
        self._log_window.setBackgroundColor_(NSColor.clearColor())
        self._log_window.setLevel_(24)  # UFO (25) の 1 段下
        self._log_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._log_window.setHasShadow_(False)

        # ドラッグ可能な背景ビュー（角丸・半透明ダーク）
        bg = LogPanelView.alloc().initWithFrame_(
            CGRectMake(0, 0, LOG_PANEL_W, LOG_PANEL_H)
        )
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.05, 0.05, 0.88).CGColor()
        )
        bg.layer().setCornerRadius_(12.0)

        # スクロール可能なテキストビュー
        p = LOG_PANEL_PADDING
        inner_w = LOG_PANEL_W - p * 2
        inner_h = LOG_PANEL_H - p * 2
        scroll = NSScrollView.alloc().initWithFrame_(CGRectMake(p, p, inner_w, inner_h))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)

        self._log_text = NSTextView.alloc().initWithFrame_(
            CGRectMake(0, 0, inner_w, inner_h)
        )
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

    def _show_log_panel(self):
        self._log_window.orderFrontRegardless()
        self._log_panel_visible = True
        self._log_panel_item.setTitle_("📝 ログ非表示")

    def _hide_log_panel(self):
        self._log_window.orderOut_(None)
        self._log_panel_visible = False
        self._log_panel_item.setTitle_("📝 ログ表示")

    @objc.typedSelector(b"v@:@")
    def toggleLogPanel_(self, sender):
        if self._log_panel_visible:
            self._hide_log_panel()
        else:
            self._show_log_panel()

    @objc.typedSelector(b"v@:@")
    def drainLogQueue_(self, timer):
        """ログキューをメインスレッドで処理してテキストビューを更新する。"""
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
        """ログ行リストを緑の等幅フォントで表示する。"""
        text = "\n".join(self._log_lines)
        font = (
            NSFont.fontWithName_size_("Menlo", 10)
            or NSFont.monospacedSystemFontOfSize_weight_(10, 0)
        )
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.2, 0.95, 0.45, 1.0)
        attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
        self._log_text.textStorage().setAttributedString_(
            NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        )
        self._log_text.scrollRangeToVisible_((len(text), 0))

    # -----------------------------------------------------------------------
    # メッセージパネル（Telegram チャット）
    # -----------------------------------------------------------------------

    def _setup_message_panel(self):
        """
        UFO 直下に表示するチャットパネルを生成する。
        上部: 送受信履歴（NSTextView）
        下部: 入力フィールド（NSTextField、Enter で送信）
        パネル板自体は透明、各メッセージに個別の背景色を付ける。
        """
        self._msg_panel_visible = False

        # KeyableWindow: ボーダレスでもキーボード入力を受け付ける
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

        # 透明な背景コンテナ
        bg = NSView.alloc().initWithFrame_(CGRectMake(0, 0, MSG_PANEL_W, MSG_PANEL_H))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.clearColor().CGColor())

        p = 7    # パディング
        gap = 5  # 入力欄とチャット欄の隙間

        # 入力フィールド（下部）
        self._msg_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(p, p, MSG_PANEL_W - p * 2, MSG_INPUT_H)
        )
        self._msg_field.setPlaceholderString_("")
        self._msg_field.setBezeled_(False)
        self._msg_field.setDrawsBackground_(False)
        self._msg_field.setTextColor_(NSColor.darkGrayColor())
        self._msg_field.setFont_(NSFont.systemFontOfSize_(12))
        self._msg_field.setFocusRingType_(1)  # NSFocusRingTypeNone: クリック時の水色枠を消す
        self._msg_field.setAction_("sendTelegramMessage:")
        self._msg_field.setTarget_(self)

        # チャット履歴表示エリア（上部）
        chat_y = p + MSG_INPUT_H + gap
        chat_w = MSG_PANEL_W - p * 2
        scroll = NSScrollView.alloc().initWithFrame_(
            CGRectMake(p, chat_y, chat_w, MSG_CHAT_H)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)

        self._chat_text = NSTextView.alloc().initWithFrame_(
            CGRectMake(0, 0, chat_w, MSG_CHAT_H)
        )
        self._chat_text.setEditable_(False)
        self._chat_text.setSelectable_(False)
        self._chat_text.setDrawsBackground_(False)
        self._chat_text.setVerticallyResizable_(True)
        self._chat_text.setHorizontallyResizable_(False)
        self._chat_text.textContainer().setWidthTracksTextView_(True)
        self._chat_text.setMinSize_((chat_w, MSG_CHAT_H))
        self._chat_text.setMaxSize_((chat_w, 1e8))
        self._chat_font = NSFont.systemFontOfSize_(11)

        scroll.setDocumentView_(self._chat_text)
        bg.addSubview_(scroll)
        bg.addSubview_(self._msg_field)
        self._msg_window.contentView().addSubview_(bg)

    def _update_msg_panel_position(self):
        """UFO ウィンドウの直下にメッセージパネルを配置する。"""
        if not self._msg_panel_visible:
            return
        frame = self._window.frame()
        mx = frame.origin.x + (UFO_SIZE - MSG_PANEL_W) / 2
        my = frame.origin.y - MSG_PANEL_H - 5
        self._msg_window.setFrameOrigin_(CGPointMake(mx, my))

    def _show_msg_panel(self):
        self._hide_ocr_panel()
        self._hide_launcher_panel()
        self._msg_panel_visible = True  # 先にセットしないと位置更新がスキップされる
        self._update_msg_panel_position()
        self._msg_window.orderFrontRegardless()
        self._msg_panel_item.setTitle_("✉️ メッセージ欄を非表示")

    def _hide_msg_panel(self):
        self._msg_window.orderOut_(None)
        self._msg_panel_visible = False
        self._msg_panel_item.setTitle_("✉️ メッセージ欄")

    @objc.typedSelector(b"v@:@")
    def toggleMsgPanel_(self, sender):
        if self._msg_panel_visible:
            self._hide_msg_panel()
        else:
            self._show_msg_panel()

    @objc.typedSelector(b"v@:@")
    def drainChatQueue_(self, timer):
        """チャットキューをメインスレッドで処理してチャット表示を更新する。"""
        if not self._chat_queue:
            return
        while self._chat_queue:
            try:
                direction, text = self._chat_queue.popleft()
                self._chat_messages.append((direction, text))
            except IndexError:
                break
        self._refresh_chat_view()

    def _refresh_chat_view(self):
        """
        チャット履歴を再描画する。
        送信メッセージ: グレー背景 + ダークグレー文字（→ prefix）
        受信メッセージ: 水色背景 + ブルー文字（← prefix）
        各メッセージの間に小さなスペーサーを挿入して区切りを作る。
        """
        combined = NSMutableAttributedString.alloc().init()
        sent_fg = NSColor.colorWithSRGBRed_green_blue_alpha_(0.2,  0.2,  0.2,  1.0)
        recv_fg = NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.3,  0.6,  1.0)
        sent_bg = NSColor.colorWithSRGBRed_green_blue_alpha_(0.82, 0.82, 0.82, 0.55)
        recv_bg = NSColor.colorWithSRGBRed_green_blue_alpha_(0.78, 0.88, 0.96, 0.55)
        spacer_attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(3)}

        for direction, text in self._chat_messages:
            fg = sent_fg if direction == "sent" else recv_fg
            bg = sent_bg if direction == "sent" else recv_bg
            prefix = "→  " if direction == "sent" else "←  "
            attrs = {
                NSFontAttributeName: self._chat_font,
                NSForegroundColorAttributeName: fg,
                NSBackgroundColorAttributeName: bg,
            }
            combined.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(prefix + text, attrs)
            )
            # 背景色なしの改行でメッセージ間に区切りを作る
            combined.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_("\n", spacer_attrs)
            )

        self._chat_text.textStorage().setAttributedString_(combined)
        self._chat_text.scrollRangeToVisible_((combined.length(), 0))

    @objc.typedSelector(b"v@:@")
    def clearChat_(self, sender):
        """チャット履歴を全消去する。"""
        self._chat_messages.clear()
        self._refresh_chat_view()

    # -----------------------------------------------------------------------
    # OCR パネル（glm-ocr via Ollama）
    # -----------------------------------------------------------------------

    def _setup_ocr_panel(self):
        """glm-ocr の結果を表示する半透明ダークパネルを生成する。初期は非表示。"""
        self._ocr_panel_visible = False

        self._ocr_window = KeyableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(0, 0, OCR_PANEL_W, OCR_PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._ocr_window.setOpaque_(False)
        self._ocr_window.setBackgroundColor_(NSColor.clearColor())
        self._ocr_window.setLevel_(25)
        self._ocr_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._ocr_window.setHasShadow_(False)

        bg = NSView.alloc().initWithFrame_(CGRectMake(0, 0, OCR_PANEL_W, OCR_PANEL_H))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.08, 0.08, 0.12, 0.92).CGColor()
        )
        bg.layer().setCornerRadius_(12.0)

        # ボタン行1（最下部）: コピー / 閉じる
        btn_w = (OCR_PANEL_W - OCR_PAD * 2 - 6) // 2
        copy_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(OCR_PAD, OCR_PAD, btn_w, OCR_BTN_H)
        )
        copy_btn.setTitle_("コピー")
        copy_btn.setBezelStyle_(1)
        copy_btn.setAction_("copyOCRText:")
        copy_btn.setTarget_(self)

        close_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(OCR_PAD + btn_w + 6, OCR_PAD, btn_w, OCR_BTN_H)
        )
        close_btn.setTitle_("閉じる")
        close_btn.setBezelStyle_(1)
        close_btn.setAction_("closeOCRPanel:")
        close_btn.setTarget_(self)

        # ボタン行2（翻訳）: 日本語 / English / 中文
        row2_y = OCR_PAD + OCR_BTN_H + 6
        btn_w3 = (OCR_PANEL_W - OCR_PAD * 2 - 10) // 3
        for i, (title, action) in enumerate([
            ("日本語", "translateJA:"),
            ("English", "translateEN:"),
            ("中文",   "translateZH:"),
        ]):
            bx = OCR_PAD + i * (btn_w3 + 5)
            btn = NSButton.alloc().initWithFrame_(CGRectMake(bx, row2_y, btn_w3, OCR_BTN_H))
            btn.setTitle_(title)
            btn.setBezelStyle_(1)
            btn.setAction_(action)
            btn.setTarget_(self)
            bg.addSubview_(btn)

        # テキスト表示エリア（上部）
        text_y = row2_y + OCR_BTN_H + OCR_PAD
        text_h = OCR_PANEL_H - text_y - OCR_PAD
        inner_w = OCR_PANEL_W - OCR_PAD * 2

        scroll = NSScrollView.alloc().initWithFrame_(
            CGRectMake(OCR_PAD, text_y, inner_w, text_h)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)

        self._ocr_text_view = NSTextView.alloc().initWithFrame_(
            CGRectMake(0, 0, inner_w, text_h)
        )
        self._ocr_text_view.setEditable_(False)
        self._ocr_text_view.setSelectable_(True)
        self._ocr_text_view.setDrawsBackground_(False)
        self._ocr_text_view.setVerticallyResizable_(True)
        self._ocr_text_view.setHorizontallyResizable_(False)
        self._ocr_text_view.textContainer().setWidthTracksTextView_(True)
        self._ocr_text_view.setMinSize_((inner_w, text_h))
        self._ocr_text_view.setMaxSize_((inner_w, 1e8))

        scroll.setDocumentView_(self._ocr_text_view)
        bg.addSubview_(scroll)
        bg.addSubview_(copy_btn)
        bg.addSubview_(close_btn)
        self._ocr_window.contentView().addSubview_(bg)

    def _show_ocr_panel(self):
        self._hide_msg_panel()
        self._hide_launcher_panel()
        self._ocr_panel_visible = True
        self._update_ocr_panel_position()
        self._ocr_window.orderFrontRegardless()

    def _hide_ocr_panel(self):
        self._ocr_window.orderOut_(None)
        self._ocr_panel_visible = False

    def _update_ocr_panel_position(self):
        """UFO ウィンドウの直下に OCR パネルを配置する。"""
        if not self._ocr_panel_visible:
            return
        frame = self._window.frame()
        mx = frame.origin.x + (UFO_SIZE - OCR_PANEL_W) / 2
        my = frame.origin.y - OCR_PANEL_H - 5
        self._ocr_window.setFrameOrigin_(CGPointMake(mx, my))

    def _refresh_ocr_view(self, text):
        """OCR テキストビューをライトグレー等幅フォントで更新する。"""
        font = NSFont.systemFontOfSize_(12)
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.9, 0.9, 0.9, 1.0)
        attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
        self._ocr_text_view.textStorage().setAttributedString_(
            NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        )
        self._ocr_text_view.scrollRangeToVisible_((0, 0))

    @objc.typedSelector(b"v@:@")
    def drainOCRQueue_(self, timer):
        """OCR 結果キューをメインスレッドで処理してパネルを更新する。"""
        if not self._ocr_result_queue:
            return
        text, is_final = None, False
        while self._ocr_result_queue:
            try:
                text, is_final = self._ocr_result_queue.popleft()
            except IndexError:
                break
        if text is not None:
            if is_final:
                self._ocr_final_text = text
                self._ocr_original_text = text  # 翻訳元として保持
            self._refresh_ocr_view(text)

    @objc.typedSelector(b"v@:@")
    def copyOCRText_(self, sender):
        """OCR 結果をクリップボードにコピーする。"""
        if not self._ocr_final_text:
            return
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(self._ocr_final_text, "public.utf8-plain-text")

    @objc.typedSelector(b"v@:@")
    def closeOCRPanel_(self, sender):
        self._hide_ocr_panel()

    # -----------------------------------------------------------------------
    # ショートカット登録パネル
    # -----------------------------------------------------------------------

    def _load_launchers(self):
        """~/.ufo_config.json から launchers リストを読み込む。"""
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            return [
                {"label": str(e.get("label", "")), "url": str(e.get("url", ""))}
                for e in data.get("launchers", [])
                if e.get("label") and e.get("url")
            ]
        except Exception:
            return []

    def _save_launchers(self):
        """launchers リストを ~/.ufo_config.json に保存する。"""
        try:
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data["launchers"] = self._launchers
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log_queue.append(f"[Launcher] 保存エラー: {e}")

    def _setup_launcher_panel(self):
        """ショートカット登録パネルを生成する。初期は非表示。"""
        self._launcher_panel_visible = False

        self._launcher_window = KeyableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(0, 0, LAUNCHER_PANEL_W, LAUNCHER_PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._launcher_window.setOpaque_(False)
        self._launcher_window.setBackgroundColor_(NSColor.clearColor())
        self._launcher_window.setLevel_(25)
        self._launcher_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._launcher_window.setHasShadow_(False)

        self._launcher_bg = NSView.alloc().initWithFrame_(
            CGRectMake(0, 0, LAUNCHER_PANEL_W, LAUNCHER_PANEL_H)
        )
        self._launcher_bg.setWantsLayer_(True)
        self._launcher_bg.layer().setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.08, 0.08, 0.12, 0.92).CGColor()
        )
        self._launcher_bg.layer().setCornerRadius_(12.0)

        inner_w = LAUNCHER_PANEL_W - LAUNCHER_PAD * 2

        # 閉じるボタン（最下部）
        close_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PANEL_W - LAUNCHER_PAD - 80, LAUNCHER_PAD, 80, 26)
        )
        close_btn.setTitle_("閉じる")
        close_btn.setBezelStyle_(1)
        close_btn.setAction_("closeLauncherPanel:")
        close_btn.setTarget_(self)
        self._launcher_bg.addSubview_(close_btn)

        # 入力行（閉じるの上）
        input_y = LAUNCHER_PAD + 26 + 6
        add_w = 50
        label_w = 80
        url_w = inner_w - label_w - add_w - 8

        self._launcher_label_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PAD, input_y, label_w, 26)
        )
        self._launcher_label_field.setPlaceholderString_("名前")
        self._launcher_label_field.setBezeled_(True)
        self._launcher_label_field.setDrawsBackground_(True)
        self._launcher_bg.addSubview_(self._launcher_label_field)

        self._launcher_url_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PAD + label_w + 4, input_y, url_w, 26)
        )
        self._launcher_url_field.setPlaceholderString_("https://...")
        self._launcher_url_field.setBezeled_(True)
        self._launcher_url_field.setDrawsBackground_(True)
        self._launcher_bg.addSubview_(self._launcher_url_field)

        add_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PAD + label_w + 4 + url_w + 4, input_y, add_w, 26)
        )
        add_btn.setTitle_("追加")
        add_btn.setBezelStyle_(1)
        add_btn.setAction_("addLauncher:")
        add_btn.setTarget_(self)
        self._launcher_bg.addSubview_(add_btn)

        # リスト表示エリア（スクロール）
        list_y = input_y + 26 + LAUNCHER_PAD
        list_h = LAUNCHER_PANEL_H - list_y - LAUNCHER_PAD

        self._launcher_scroll = NSScrollView.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PAD, list_y, inner_w, list_h)
        )
        self._launcher_scroll.setHasVerticalScroller_(True)
        self._launcher_scroll.setAutohidesScrollers_(True)
        self._launcher_scroll.setBorderType_(0)
        self._launcher_scroll.setDrawsBackground_(False)
        self._launcher_bg.addSubview_(self._launcher_scroll)

        self._launcher_window.contentView().addSubview_(self._launcher_bg)
        self._rebuild_launcher_list_view()

    def _rebuild_launcher_list_view(self):
        """ショートカット一覧を再描画する。"""
        inner_w = LAUNCHER_PANEL_W - LAUNCHER_PAD * 2
        gap = 4
        n = len(self._launchers)
        content_h = max(n * (LAUNCHER_ROW_H + gap), 40)

        content_view = NSView.alloc().initWithFrame_(CGRectMake(0, 0, inner_w, content_h))

        for i, entry in enumerate(self._launchers):
            # y=0 が下端なので上から順に並べるため逆算
            row_y = content_h - (i + 1) * (LAUNCHER_ROW_H + gap)

            del_btn = NSButton.alloc().initWithFrame_(
                CGRectMake(inner_w - 26, row_y + 2, 22, 22)
            )
            del_btn.setTitle_("×")
            del_btn.setBezelStyle_(1)
            del_btn.setTag_(i)
            del_btn.setAction_("deleteLauncherByTag:")
            del_btn.setTarget_(self)
            content_view.addSubview_(del_btn)

            label_field = NSTextField.alloc().initWithFrame_(
                CGRectMake(0, row_y, 95, LAUNCHER_ROW_H)
            )
            label_field.setStringValue_(entry["label"])
            label_field.setEditable_(False)
            label_field.setBezeled_(False)
            label_field.setDrawsBackground_(False)
            label_field.setTextColor_(
                NSColor.colorWithSRGBRed_green_blue_alpha_(0.9, 0.9, 0.9, 1.0)
            )
            label_field.setFont_(NSFont.systemFontOfSize_(12))
            content_view.addSubview_(label_field)

            url_field = NSTextField.alloc().initWithFrame_(
                CGRectMake(99, row_y, inner_w - 99 - 30, LAUNCHER_ROW_H)
            )
            url_field.setStringValue_(entry["url"])
            url_field.setEditable_(False)
            url_field.setBezeled_(False)
            url_field.setDrawsBackground_(False)
            url_field.setTextColor_(
                NSColor.colorWithSRGBRed_green_blue_alpha_(0.55, 0.65, 0.95, 1.0)
            )
            url_field.setFont_(NSFont.systemFontOfSize_(11))
            content_view.addSubview_(url_field)

        self._launcher_scroll.setDocumentView_(content_view)

    def _rebuild_launcher_menu(self):
        """メニューの動的ランチャーアイテムを再構築する。"""
        menu = self._status_item.menu()
        for item in self._launcher_dynamic_items:
            menu.removeItem_(item)
        self._launcher_dynamic_items = []

        base_idx = menu.indexOfItem_(self._launcher_register_item) + 1
        for i, entry in enumerate(self._launchers):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"🔗 {entry['label']}", "openLauncherURL:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(entry["url"])
            menu.insertItem_atIndex_(item, base_idx + i)
            self._launcher_dynamic_items.append(item)

    def _show_launcher_panel(self):
        self._hide_msg_panel()
        self._hide_ocr_panel()
        self._launcher_panel_visible = True
        self._update_launcher_panel_position()
        self._launcher_window.orderFrontRegardless()

    def _hide_launcher_panel(self):
        if not hasattr(self, "_launcher_panel_visible"):
            return
        self._launcher_window.orderOut_(None)
        self._launcher_panel_visible = False

    def _update_launcher_panel_position(self):
        """UFO ウィンドウの直下にランチャーパネルを配置する。"""
        if not self._launcher_panel_visible:
            return
        frame = self._window.frame()
        mx = frame.origin.x + (UFO_SIZE - LAUNCHER_PANEL_W) / 2
        my = frame.origin.y - LAUNCHER_PANEL_H - 5
        self._launcher_window.setFrameOrigin_(CGPointMake(mx, my))

    @objc.typedSelector(b"v@:@")
    def showLauncherPanel_(self, sender):
        if self._launcher_panel_visible:
            self._hide_launcher_panel()
        else:
            self._show_launcher_panel()

    @objc.typedSelector(b"v@:@")
    def closeLauncherPanel_(self, sender):
        self._hide_launcher_panel()

    @objc.typedSelector(b"v@:@")
    def addLauncher_(self, sender):
        label = self._launcher_label_field.stringValue().strip()
        url = self._launcher_url_field.stringValue().strip()
        if not label or not url:
            return
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        self._launchers.append({"label": label, "url": url})
        self._save_launchers()
        self._launcher_label_field.setStringValue_("")
        self._launcher_url_field.setStringValue_("")
        self._rebuild_launcher_list_view()
        self._rebuild_launcher_menu()

    @objc.typedSelector(b"v@:@")
    def deleteLauncherByTag_(self, sender):
        idx = sender.tag()
        if 0 <= idx < len(self._launchers):
            self._launchers.pop(idx)
            self._save_launchers()
            self._rebuild_launcher_list_view()
            self._rebuild_launcher_menu()

    @objc.typedSelector(b"v@:@")
    def openLauncherURL_(self, sender):
        url = sender.representedObject()
        if url:
            subprocess.Popen(["open", url])

    # 翻訳ボタン（translategemma:4b）
    @objc.typedSelector(b"v@:@")
    def translateJA_(self, sender):
        self._start_translate("Japanese")

    @objc.typedSelector(b"v@:@")
    def translateEN_(self, sender):
        self._start_translate("English")

    @objc.typedSelector(b"v@:@")
    def translateZH_(self, sender):
        self._start_translate("Chinese")

    def _start_translate(self, lang):
        """翻訳をバックグラウンドスレッドで開始する。"""
        src = self._ocr_original_text.strip()
        if not src:
            return
        self._refresh_ocr_view(f"翻訳中 ({lang})...")
        threading.Thread(
            target=self._run_translate,
            args=(src, lang),
            daemon=True,
        ).start()

    def _run_translate(self, text, lang):
        """バックグラウンドスレッドで translategemma:4b を呼び出す。"""
        if not self._ensure_ollama_running():
            self._ocr_result_queue.append((
                "Ollama に接続できませんでした。",
                False,
            ))
            return

        prompt = f"Translate the following text to {lang}. Output only the translation, no explanations:\n\n{text}"
        try:
            payload = json.dumps({
                "model": "translategemma:4b",
                "prompt": prompt,
                "stream": False,
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            translated = result.get("response", "").strip() or "(翻訳結果なし)"
            self._ocr_result_queue.append((translated, False))
        except Exception as e:
            self._ocr_result_queue.append((f"翻訳エラー: {e}", False))

    @objc.typedSelector(b"v@:@")
    def startOCR_(self, sender):
        """ufocapture フォルダからファイルを選択して glm-ocr で OCR 解析する。"""
        capture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ufocapture")
        os.makedirs(capture_dir, exist_ok=True)

        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setAllowedFileTypes_(["png", "jpg", "jpeg"])
        panel.setTitle_("OCR する画像を選択")
        panel.setDirectoryURL_(NSURL.fileURLWithPath_(capture_dir))

        if panel.runModal() != 1:
            return  # キャンセル

        image_path = panel.URL().path()
        self._ocr_final_text = ""
        self._show_ocr_panel()
        self._refresh_ocr_view("解析中...")

        threading.Thread(
            target=self._run_ocr,
            args=(image_path,),
            daemon=True,
        ).start()

    @objc.typedSelector(b"v@:@")
    def openNFTPages_(self, sender):
        """Pinata ストレージと mint サイトをブラウザで開く。"""
        import subprocess
        subprocess.Popen(["open", "https://app.pinata.cloud/ipfs/files"])
        subprocess.Popen(["open", "https://sui-mint.torus-studio.tech/"])

    @objc.typedSelector(b"v@:@")
    def launchClaudeCode_(self, sender):
        """Terminal を開いて UFO プロジェクトで claude を起動する。"""
        import subprocess
        project_dir = os.path.dirname(os.path.abspath(__file__))
        script = f'tell application "Terminal" to do script "cd {project_dir} && claude"'
        subprocess.Popen(["osascript", "-e", script])

    def _check_ollama_api(self):
        """Ollama API (localhost:11434) に接続できるか確認する。"""
        try:
            urllib.request.urlopen("http://localhost:11434", timeout=2)
            return True
        except Exception:
            return False

    def _ensure_ollama_running(self):
        """Ollama が起動していなければ起動して、最大15秒待つ。"""
        if self._check_ollama_api():
            return True
        self._ocr_result_queue.append(("Ollama 起動中...", False))
        try:
            subprocess.Popen(
                ["open", "-a", "Ollama"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                return False
        for _ in range(15):
            time.sleep(1)
            if self._check_ollama_api():
                return True
        return False

    def _run_ocr(self, image_path):
        """バックグラウンドスレッドで Ollama glm-ocr を呼び出す。"""
        if not self._ensure_ollama_running():
            self._ocr_result_queue.append((
                "Ollama に接続できませんでした。\nOllama が起動しているか確認してください。",
                True,
            ))
            return

        self._ocr_result_queue.append(("解析中...", False))
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = json.dumps({
                "model": "glm-ocr",
                "prompt": "この画像に含まれるすべてのテキストを読み取って書き起こしてください。",
                "images": [image_b64],
                "stream": False,
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            text = result.get("response", "").strip() or "(テキストが見つかりませんでした)"
            self._ocr_result_queue.append((text, True))
        except Exception as e:
            self._ocr_result_queue.append((f"エラー: {e}", True))

    # -----------------------------------------------------------------------
    # Telegram 送信
    # -----------------------------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def sendTelegramMessage_(self, sender):
        """入力フィールドのテキストを Telegram に送信する。"""
        text = self._msg_field.stringValue().strip()
        if not text:
            return
        config = tg.load_config()
        if not config:
            self._log_queue.append(
                "[Telegram] 未設定: ~/.ufo_config.json か ~/.nanobot/config.json を確認してください"
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
        self._chat_queue.append(("sent", text))  # チャット欄に即時表示

        def _send():
            try:
                tg.send_message(token, chat_id, text)
            except Exception as e:
                self._log_queue.append(f"[Telegram] 送信エラー: {e}")

        threading.Thread(target=_send, daemon=True).start()

    @objc.typedSelector(b"v@:@")
    def showTelegramStatus_(self, sender):
        """現在の Telegram 設定状況をログパネルに表示する。"""
        config = tg.load_config()
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

    # -----------------------------------------------------------------------
    # nanobot ゲートウェイ制御
    # -----------------------------------------------------------------------

    def _is_nanobot_running(self):
        return self._nanobot_proc is not None and self._nanobot_proc.poll() is None

    @objc.typedSelector(b"v@:@")
    def toggleNanobot_(self, sender):
        if self._is_nanobot_running():
            self._stop_nanobot()
        else:
            self._start_nanobot()

    def _start_nanobot(self):
        if self._is_nanobot_running():
            return

        # nanobot が getUpdates を使うため UFO 側のポーリングを停止
        self._tg_poller.stop()

        # ログをクリアしてパネルを表示
        self._log_lines.clear()
        self._log_queue.clear()
        self._refresh_log_view()
        self._show_log_panel()

        # uv run nanobot gateway を起動（uv が見つからなければ venv 直接実行）
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

        # stdout をバックグラウンドスレッドで読んでログキューに積む
        threading.Thread(
            target=self._read_nanobot_output,
            args=(self._nanobot_proc,),
            daemon=True,
        ).start()

        self._nanobot_item.setTitle_("🐈 nanobot停止")
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
        self._nanobot_item.setTitle_("🐈 nanobot起動")
        self._update_menu_bar_icon()

        # nanobot 停止後に UFO 側のポーリングを再開
        self._tg_poller.start()

    def _read_nanobot_output(self, proc):
        """nanobot の stdout をバックグラウンドで読み続けてキューに積む。"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._log_queue.append(line)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 自動起動 (Launch Agent)
    # -----------------------------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def toggleAutostart_(self, sender):
        """ログイン時自動起動のオン/オフを切り替える。"""
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        self._autostart_item.setState_(1 if autostart.is_enabled() else 0)

    # -----------------------------------------------------------------------
    # メニューバー
    # -----------------------------------------------------------------------

    def _setup_menu_bar(self):
        """メニューバーアイコンとドロップダウンメニューを構築する。"""
        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(-1)
        self._update_menu_bar_icon()

        menu = NSMenu.alloc().init()

        # UFO 表示/非表示
        self._hide_item = self._make_menu_item("UFO を隠す", "toggleHide:", "u", menu)
        menu.addItem_(NSMenuItem.separatorItem())

        # Claude Code 起動
        self._make_menu_item("⚡️ claude code起動", "launchClaudeCode:", "c", menu)

        # nanobot ゲートウェイ
        self._nanobot_item = self._make_menu_item("🐈 nanobot起動", "toggleNanobot:", "n", menu)

        # メッセージパネル
        self._msg_panel_item = self._make_menu_item("✉️ メッセージ欄", "toggleMsgPanel:", "m", menu)

        # OCR 解析
        self._make_menu_item("🔍 OCR 解析", "startOCR:", "o", menu)

        # NFT 作成
        self._make_menu_item("🎖️ NFT作成", "openNFTPages:", "", menu)

        menu.addItem_(NSMenuItem.separatorItem())

        # ショートカット登録
        self._launcher_register_item = self._make_menu_item(
            "✏️ ショートカット登録", "showLauncherPanel:", "", menu
        )
        # 登録済みランチャー（動的）をここに挿入
        self._rebuild_launcher_menu()

        # ログパネル
        self._log_panel_item = self._make_menu_item("📝 ログ表示", "toggleLogPanel:", "l", menu)

        # チャットクリア
        self._make_menu_item("🧹 チャットクリア", "clearChat:", "", menu)

        menu.addItem_(NSMenuItem.separatorItem())

        # 自動起動（チェックマークで現在状態を表示）
        self._autostart_item = self._make_menu_item(
            "ログイン時に自動起動", "toggleAutostart:", "", menu
        )
        self._autostart_item.setState_(1 if autostart.is_enabled() else 0)

        menu.addItem_(NSMenuItem.separatorItem())

        self._status_item.setMenu_(menu)

    def _make_menu_item(self, title, action, key, menu):
        """NSMenuItem を生成して menu に追加し、返す。"""
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self)
        menu.addItem_(item)
        return item

    def _update_menu_bar_icon(self):
        """稼働状態に合わせてメニューバーのドット絵アイコンを更新する。"""
        if self._chat_flash_ticks > 0:
            img = self._icon_chat
        elif self._is_nanobot_running():
            img = self._icon_active_a if (self._icon_tick // 15) % 2 == 0 else self._icon_active_b
        else:
            img = self._icon_idle
        btn = self._status_item.button()
        btn.setTitle_("")
        btn.setImage_(img)

    # -----------------------------------------------------------------------
    # アプリ終了
    # -----------------------------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        self._stop_nanobot()
        NSApp.terminate_(None)

    def applicationWillTerminate_(self, notification):
        self._stop_nanobot()
