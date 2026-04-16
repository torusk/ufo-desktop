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
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
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
from views import ClickableView, KeyableWindow, LogPanelView, ResizeHandleView

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

# メッセージパネルのサイズ（固定・ドラッグ可能、UFO 非連動）
MSG_PANEL_W = 280
MSG_PANEL_H = 320
MSG_CHAT_H = 262   # チャット表示エリアの高さ
MSG_INPUT_H = 34   # 入力行の高さ

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
        """
        アプリ起動完了時に呼ばれる AppKit コールバック。
        状態変数の初期化 → UI 構築 → タイマー登録 → Telegram ポーリング開始 の順に実行する。
        """
        # Dock に表示しないアクセサリアプリとして動作（メニューバーのみ）
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # --- 状態変数の初期化 ---
        self._nanobot_proc = None
        self._ufo_chat_active = False  # デスクトップから nanobot agent に直接送信するモード

        # ドット絵アイコンを生成・ロード
        icons.generate_all()
        self._load_menu_icons()

        # メニューバーアイコン切り替え用カウンター（animationTick_ で増加）
        self._icon_tick = 0
        # >0 の間、メニューバーをチャット受信アイコンに切り替える（約 0.5秒×N）
        self._chat_flash_ticks = 0

        # UFO ウィンドウの非表示フラグ（"UFO を隠す" で切り替え）
        self._ufo_hidden = False

        # チャットパネル用
        # _chat_messages: 表示済みメッセージのリスト（direction, text） のタプルのリスト
        #   direction: "sent"（送信）/ "recv"（受信・nanobot）/ "sys"（システム通知）
        # _chat_queue: バックグラウンドスレッドからの受け渡しキュー（deque はスレッドセーフ）
        self._chat_messages = []
        self._chat_queue = collections.deque()

        # OCR パネル用
        # _ocr_result_queue: バックグラウンドから (text, is_final) を受け渡すキュー
        # _ocr_final_text: コピーボタン用の確定テキスト
        # _ocr_original_text: 翻訳ボタン押下時の再翻訳元（OCR 直後に保存）
        self._ocr_result_queue = collections.deque()
        self._ocr_final_text = ""
        self._ocr_original_text = ""

        # ショートカット登録パネル用
        # _launchers: {"label": str, "url": str} のリスト（~/.ufo_config.json と同期）
        # _launcher_dynamic_items: メニューに動的追加した NSMenuItem のリスト（削除時に使用）
        self._launchers = self._load_launchers()
        self._launcher_dynamic_items = []

        # Telegram ポーラー（nanobot 起動中は stop() で一時停止）
        # 受信したテキストをチャットキューに積み、メニューバーをチャットアイコンに切り替える
        def _on_recv(text):
            self._chat_queue.append(("recv", text))
            self._chat_flash_ticks = 6  # 15tick × 6 ≒ 3秒間チャットアイコンを表示
        self._tg_poller = tg.TelegramPoller(on_message=_on_recv)

        # --- UI セットアップ（順序依存あり: メニューは最後に構築）---
        self._setup_ufo_window()        # UFO 画像ウィンドウ
        self._setup_message_panel()     # Telegram チャットパネル（右上固定）
        self._setup_ocr_panel()         # OCR 結果パネル（UFO 直下）
        self._setup_launcher_panel()    # ショートカット登録パネル（UFO 直下）
        self._setup_menu_bar()          # メニューバーアイコン＋メニュー
        self._start_animation()         # UFO アニメーションタイマー開始

        # バックグラウンド→メインスレッド間のキュー処理タイマー
        # NSTimer はメインスレッドの RunLoop で実行されるため UI 更新が安全
        self._add_timer("drainChatQueue:", 0.5, repeats=True)
        self._add_timer("drainOCRQueue:",  0.3, repeats=True)

        # Telegram ポーリング開始
        # nanobot 起動時は _start_nanobot() 内で stop() して競合を防ぐ
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
        """
        UFO 画像ウィンドウを生成して画面中央に配置する。

        ウィンドウは NSWindowStyleMaskBorderless（タイトルバーなし）+ 透明背景で作成し、
        level=25 で常に最前面に浮かせる。UFO.png は assets/ から読み込む。
        """
        sf = NSScreen.mainScreen().frame()
        start_x = (sf.size.width  - UFO_SIZE) / 2
        start_y = (sf.size.height - UFO_SIZE) / 2

        # 自律移動の基準座標（wobble オフセットを加える前の論理位置）
        self._pos_x = start_x
        self._pos_y = start_y
        self._target_x, self._target_y = self._random_waypoint()

        # ボーダレス・透明・最前面ウィンドウ
        # CanJoinAllSpaces: 全スペース（Mission Control の仮想デスクトップ）で表示
        # Stationary: Exposé/Spaces の操作でも動かない
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(start_x, start_y, UFO_SIZE, UFO_SIZE),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(25)  # NSStatusWindowLevel に相当
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(False)

        # UFO 画像（assets/UFO.png、透過 PNG）
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        ufo_image = NSImage.alloc().initWithContentsOfFile_(
            os.path.join(assets_dir, "UFO.png")
        )
        image_view = NSImageView.alloc().initWithFrame_(CGRectMake(0, 0, UFO_SIZE, UFO_SIZE))
        image_view.setImage_(ufo_image)
        image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        image_view.setWantsLayer_(True)

        # ClickableView: 透明なイベント受け取り層を画像の上に重ねる
        # クリック・ドラッグ・右クリックをすべてここで処理（views.py 参照）
        click_view = ClickableView.alloc().initWithFrame_(CGRectMake(0, 0, UFO_SIZE, UFO_SIZE))

        self._window.contentView().addSubview_(image_view)
        self._window.contentView().addSubview_(click_view)
        self._window.orderFrontRegardless()

    # -----------------------------------------------------------------------
    # アニメーション
    # -----------------------------------------------------------------------

    def _start_animation(self):
        """
        UFO アニメーションタイマー（30fps）を開始する。
        シングルクリックで停止・再開が切り替わる（toggleAnimation 参照）。
        """
        self._ufo_visible = True
        self._start_time = time.monotonic()
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            TIMER_INTERVAL, self, "animationTick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    @objc.typedSelector(b"v@:@")
    def animationTick_(self, timer):
        """
        30fps で呼ばれるアニメーションループ。
        ① 自律移動: ランダムなウェイポイントへ一定速度で直進し、到達したら次を選ぶ
        ② ふわふわ: サイン波 2 波（縦・横）を基準座標に重ねて揺らす
        ③ 連動パネル: OCR/ランチャーパネルを UFO 直下に追従させる
        ④ アイコン: 15tick ごとにメニューバーアイコンを更新
        """
        t = time.monotonic() - self._start_time

        if not self._ufo_hidden:
            # ① 自律移動（ウェイポイントへ直進）
            dx = self._target_x - self._pos_x
            dy = self._target_y - self._pos_y
            dist = math.hypot(dx, dy)
            if dist < ARRIVE_THRESHOLD:
                # 近づいたら次の目標点をランダムに選択
                self._target_x, self._target_y = self._random_waypoint()
            else:
                # 方向ベクトルを正規化してスピードを掛けて移動
                self._pos_x += (dx / dist) * ROAM_SPEED
                self._pos_y += (dy / dist) * ROAM_SPEED

            # ② ふわふわ wobble（サイン波 2 つ）
            # 縦方向: 周期 WOBBLE_PERIOD 秒、振れ幅 WOBBLE_Y_AMP px
            # 横方向: 縦より 1.6 倍遅い周期でゆっくり揺れる
            wobble_y = WOBBLE_Y_AMP * math.sin(2.0 * math.pi * t / WOBBLE_PERIOD)
            wobble_x = WOBBLE_X_AMP * math.sin(2.0 * math.pi * t / (WOBBLE_PERIOD * 1.6))

            self._window.setFrameOrigin_(
                CGPointMake(self._pos_x + wobble_x, self._pos_y + wobble_y)
            )

            # ③ 連動パネル位置更新（表示中のみ内部で早期リターン）
            self._update_ocr_panel_position()
            self._update_launcher_panel_position()

        # ④ メニューバーアイコンを 15tick（≒ 0.5秒）ごとに更新
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
    # メッセージパネル（Telegram チャット）
    # -----------------------------------------------------------------------

    def _setup_message_panel(self):
        """
        固定チャットパネル（Telegram 送受信 + nanobot 出力）を生成する。

        構造:
          ┌──────────────────────┐
          │ チャット履歴スクロール │  ← NSTextView（LINE 風左右配置）
          ├──────────────────────┤
          │ 入力欄     │ 送信ボタン│  ← NSTextField + NSButton
          └◤────────────────────┘
           ↑ リサイズハンドル（左下）

        - KeyableWindow: ボーダレスでもキーボード入力を受け付けるサブクラス
        - LogPanelView: 背景ビューをドラッグで移動できるサブクラス
        - ResizeHandleView: 左下ドラッグで右上固定リサイズ
        - メッセージパネルは UFO と連動しない（固定位置・独立ドラッグ）
        """
        self._msg_panel_visible = False

        sf = NSScreen.mainScreen().frame()
        # デフォルト位置: 画面右上（メニューバー 40px 分を引いて隙間を確保）
        init_x = sf.size.width  - MSG_PANEL_W - 20
        init_y = sf.size.height - MSG_PANEL_H - 40

        self._msg_window = KeyableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            CGRectMake(init_x, init_y, MSG_PANEL_W, MSG_PANEL_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._msg_window.setOpaque_(False)
        self._msg_window.setBackgroundColor_(NSColor.clearColor())
        self._msg_window.setLevel_(24)
        self._msg_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        self._msg_window.setHasShadow_(True)

        # LogPanelView でドラッグ移動可能な背景
        bg = LogPanelView.alloc().initWithFrame_(
            CGRectMake(0, 0, MSG_PANEL_W, MSG_PANEL_H)
        )
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.96, 0.97, 0.96).CGColor()
        )
        bg.layer().setCornerRadius_(12.0)

        p = 8
        send_w = 46
        field_w = MSG_PANEL_W - p * 2 - send_w - 6

        # 入力欄（最下部）
        self._msg_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(p, p, field_w, MSG_INPUT_H)
        )
        self._msg_field.setPlaceholderString_("Telegramへ送信… (Enter)")
        self._msg_field.setBezeled_(True)
        self._msg_field.setDrawsBackground_(True)
        self._msg_field.setTextColor_(NSColor.darkGrayColor())
        self._msg_field.setFont_(NSFont.systemFontOfSize_(12))
        self._msg_field.setFocusRingType_(1)
        self._msg_field.setAction_("sendTelegramMessage:")
        self._msg_field.setTarget_(self)

        send_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(p + field_w + 6, p, send_w, MSG_INPUT_H)
        )
        send_btn.setTitle_("送信")
        send_btn.setBezelStyle_(1)
        send_btn.setAction_("sendTelegramMessage:")
        send_btn.setTarget_(self)

        # チャット履歴（入力欄の上）
        chat_y = p + MSG_INPUT_H + 6
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
        self._chat_font = NSFont.systemFontOfSize_(12)

        scroll.setDocumentView_(self._chat_text)

        # リサイズハンドル（左下コーナー）
        handle = ResizeHandleView.alloc().initWithFrame_(CGRectMake(0, 0, 24, 24))
        handle.setWantsLayer_(True)
        handle.layer().setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.5, 0.5, 0.55, 0.25).CGColor()
        )
        handle.layer().setCornerRadius_(4.0)

        # サブビュー参照を保存（リサイズ時に再配置）
        self._msg_bg       = bg
        self._msg_scroll   = scroll
        self._msg_send_btn = send_btn

        bg.addSubview_(scroll)
        bg.addSubview_(self._msg_field)
        bg.addSubview_(send_btn)
        bg.addSubview_(handle)
        self._msg_window.contentView().addSubview_(bg)

    def _show_msg_panel(self):
        self._msg_panel_visible = True
        self._update_chat_mode()
        NSApp.activateIgnoringOtherApps_(True)
        self._msg_window.makeKeyAndOrderFront_(None)
        self._msg_window.makeFirstResponder_(self._msg_field)
        self._msg_panel_item.setTitle_("✉️ Telegram接続 非表示")

    def _hide_msg_panel(self):
        self._msg_window.orderOut_(None)
        self._msg_panel_visible = False
        self._msg_panel_item.setTitle_("✉️ Telegram接続")

    def resize_msg_panel(self, new_w, new_h):
        """
        ResizeHandleView からのコールバック。ウィンドウリサイズに合わせて
        すべてのサブビューの frame を再計算し、フォントサイズを比例変更する。

        呼び出し元: views.ResizeHandleView.mouseDragged_
        フォントサイズ: パネル初期高さ 320px を基準に 10〜22pt の範囲でスケール
        """
        p = 8
        send_w = 46
        field_w = new_w - p * 2 - send_w - 6
        chat_y  = p + MSG_INPUT_H + 6
        chat_w  = new_w - p * 2
        chat_h  = max(60, new_h - chat_y - p)

        self._msg_bg.setFrame_(CGRectMake(0, 0, new_w, new_h))
        self._msg_scroll.setFrame_(CGRectMake(p, chat_y, chat_w, chat_h))
        self._chat_text.setFrame_(CGRectMake(0, 0, chat_w, chat_h))
        self._chat_text.setMinSize_((chat_w, chat_h))
        self._msg_field.setFrame_(CGRectMake(p, p, field_w, MSG_INPUT_H))
        self._msg_send_btn.setFrame_(CGRectMake(p + field_w + 6, p, send_w, MSG_INPUT_H))

        # フォントサイズをパネル高さに比例させる（初期高さ 320px → 12pt 基準）
        font_size = max(10, min(22, round(12 * new_h / 320.0)))
        self._chat_font = NSFont.systemFontOfSize_(font_size)
        self._refresh_chat_view()

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
        チャット履歴を LINE 風に再描画する（全件再構築）。

        メッセージ種別と配置:
          sent: 右寄せ (alignment=1)・グレー背景   ← 自分の送信
          recv: 左寄せ (alignment=0)・水色背景      ← Telegram 受信
          recv (🤖 prefix): 左寄せ・緑背景          ← nanobot AI 応答
          sys:  中央 (alignment=2)・グレー文字      ← システム通知

        NOTE: NSTextAlignmentRight = 1（Left=0, Center=2）
        段落スタイル設定に失敗した場合は→/←記号のプレーンテキストにフォールバックする。
        """
        try:
            combined = NSMutableAttributedString.alloc().init()
            # 色定義
            sent_fg  = NSColor.colorWithSRGBRed_green_blue_alpha_(0.1,  0.1,  0.1,  1.0)
            recv_fg  = NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.25, 0.55, 1.0)
            bot_fg   = NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.40, 0.15, 1.0)
            sent_bg  = NSColor.colorWithSRGBRed_green_blue_alpha_(0.80, 0.80, 0.80, 0.80)
            recv_bg  = NSColor.colorWithSRGBRed_green_blue_alpha_(0.72, 0.88, 1.0,  0.85)
            bot_bg   = NSColor.colorWithSRGBRed_green_blue_alpha_(0.82, 0.95, 0.82, 0.85)
            sys_fg   = NSColor.colorWithSRGBRed_green_blue_alpha_(0.5,  0.5,  0.5,  1.0)
            # メッセージ間の余白（4pt フォントの改行で代用）
            spacer_attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(4)}

            for direction, text in self._chat_messages:
                is_bot = direction == "recv" and text.startswith("🤖")
                is_sys = direction == "sys"

                if is_sys:
                    para = NSMutableParagraphStyle.alloc().init()
                    para.setAlignment_(2)   # center
                    attrs = {
                        NSFontAttributeName:            NSFont.systemFontOfSize_(10),
                        NSForegroundColorAttributeName: sys_fg,
                        NSParagraphStyleAttributeName:  para,
                    }
                elif direction == "sent":
                    para = NSMutableParagraphStyle.alloc().init()
                    para.setAlignment_(1)   # right (NSTextAlignmentRight = 1)
                    para.setHeadIndent_(50)
                    attrs = {
                        NSFontAttributeName:            self._chat_font,
                        NSForegroundColorAttributeName: sent_fg,
                        NSBackgroundColorAttributeName: sent_bg,
                        NSParagraphStyleAttributeName:  para,
                    }
                else:
                    para = NSMutableParagraphStyle.alloc().init()
                    para.setAlignment_(0)   # left
                    para.setTailIndent_(-50)
                    fg = bot_fg if is_bot else recv_fg
                    bg = bot_bg if is_bot else recv_bg
                    attrs = {
                        NSFontAttributeName:            self._chat_font,
                        NSForegroundColorAttributeName: fg,
                        NSBackgroundColorAttributeName: bg,
                        NSParagraphStyleAttributeName:  para,
                    }

                combined.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(text + "\n", attrs)
                )
                combined.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_("\n", spacer_attrs)
                )

            self._chat_text.textStorage().setAttributedString_(combined)
            self._chat_text.scrollRangeToVisible_((combined.length(), 0))
        except Exception as e:
            # 段落スタイル失敗時のフォールバック（プレーンテキスト表示）
            lines = []
            for direction, text in self._chat_messages:
                if direction == "sent":
                    lines.append(f"→ {text}")
                elif direction == "sys":
                    lines.append(f"— {text} —")
                else:
                    lines.append(f"← {text}")
            plain = "\n".join(lines)
            font  = NSFont.systemFontOfSize_(12)
            color = NSColor.darkGrayColor()
            self._chat_text.textStorage().setAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    plain, {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
                )
            )

    @objc.typedSelector(b"v@:@")
    def clearChat_(self, sender):
        """チャット履歴を全消去する。"""
        self._chat_messages.clear()
        self._refresh_chat_view()

    # -----------------------------------------------------------------------
    # OCR パネル（glm-ocr via Ollama）
    # -----------------------------------------------------------------------

    def _setup_ocr_panel(self):
        """
        OCR 結果パネルを生成する（初期は非表示）。

        構造（下から上に積み上げ）:
          [コピー] [閉じる]        ← ボタン行1（最下部）
          [日本語] [English] [中文] ← ボタン行2（翻訳）
          テキスト表示スクロール    ← OCR 結果 or 翻訳結果

        使用モデル:
          OCR: glm-ocr（Ollama 経由）
          翻訳: translategemma:4b（Ollama 経由）

        位置: UFO ウィンドウの直下に追従（_update_ocr_panel_position）
        """
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
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.96, 0.97, 0.96).CGColor()
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
        """OCR テキストビューを更新する。"""
        font = NSFont.systemFontOfSize_(12)
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.1, 0.1, 0.15, 1.0)
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

    # -----------------------------------------------------------------------
    # ショートカット登録（URL ランチャー）
    # -----------------------------------------------------------------------
    # 設定は ~/.ufo_config.json の "launchers" キーに保存:
    #   {"launchers": [{"label": "ChatGPT", "url": "https://chatgpt.com"}, ...]}
    # パネルで追加/削除するたびに JSON を即時保存してメニューも再構築する。

    def _load_launchers(self):
        """~/.ufo_config.json から launchers リストを読み込む。ファイルがなければ空リスト。"""
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
            self._chat_queue.append(("sys", f"⚠️ ショートカット保存エラー: {e}"))

    def _setup_launcher_panel(self):
        """
        ショートカット登録パネルを生成する（初期は非表示）。

        構造（下から上）:
          [名前入力] [URL入力] [📋] [追加]  ← 入力行
          [            閉じる           ]  ← 最下部ボタン
          スクロールリスト: 登録済み一覧    ← ラベル + URL + [✕]

        位置: UFO ウィンドウの直下に追従（_update_launcher_panel_position）
        キー入力: KeyableWindow でアクセサリアプリでも入力可能
        📋 ボタン: アクセサリアプリでは Cmd+V が届かないためクリップボード貼り付けで代替
        """
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
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.96, 0.97, 0.96).CGColor()
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
        paste_w = 30
        label_w = 80
        url_w = inner_w - label_w - paste_w - add_w - 12

        self._launcher_label_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(LAUNCHER_PAD, input_y, label_w, 26)
        )
        self._launcher_label_field.setPlaceholderString_("名前")
        self._launcher_label_field.setBezeled_(True)
        self._launcher_label_field.setDrawsBackground_(True)
        self._launcher_bg.addSubview_(self._launcher_label_field)

        url_x = LAUNCHER_PAD + label_w + 4
        self._launcher_url_field = NSTextField.alloc().initWithFrame_(
            CGRectMake(url_x, input_y, url_w, 26)
        )
        self._launcher_url_field.setPlaceholderString_("URLをコピーして📋")
        self._launcher_url_field.setBezeled_(True)
        self._launcher_url_field.setDrawsBackground_(True)
        self._launcher_bg.addSubview_(self._launcher_url_field)

        paste_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(url_x + url_w + 4, input_y, paste_w, 26)
        )
        paste_btn.setTitle_("📋")
        paste_btn.setBezelStyle_(1)
        paste_btn.setAction_("pasteURL:")
        paste_btn.setTarget_(self)
        self._launcher_bg.addSubview_(paste_btn)

        add_btn = NSButton.alloc().initWithFrame_(
            CGRectMake(url_x + url_w + 4 + paste_w + 4, input_y, add_w, 26)
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
            del_btn.setTitle_("✕")
            del_btn.setBezelStyle_(7)  # NSBezelStyleCircular
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
                NSColor.colorWithSRGBRed_green_blue_alpha_(0.1, 0.1, 0.15, 1.0)
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
                NSColor.colorWithSRGBRed_green_blue_alpha_(0.2, 0.3, 0.7, 1.0)
            )
            url_field.setFont_(NSFont.systemFontOfSize_(11))
            content_view.addSubview_(url_field)

        self._launcher_scroll.setDocumentView_(content_view)

    def _rebuild_launcher_menu(self, menu=None):
        """
        メニューの動的ランチャーアイテム（🔗 ...）を再構築する。

        menu 引数: _setup_menu_bar() から呼ぶ際は setMenu_ 前なので直接渡す。
                   追加/削除後の再構築時は None でよい（self._status_item.menu() を使用）。
        """
        if menu is None:
            menu = self._status_item.menu()
        for item in self._launcher_dynamic_items:
            menu.removeItem_(item)
        self._launcher_dynamic_items = []

        # _launcher_register_item の次のインデックスに順番に挿入
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
        NSApp.activateIgnoringOtherApps_(True)
        self._launcher_window.makeKeyAndOrderFront_(None)
        self._launcher_window.makeFirstResponder_(self._launcher_label_field)

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
    def pasteURL_(self, sender):
        """クリップボードの内容を URL フィールドに貼り付ける。"""
        pb = NSPasteboard.generalPasteboard()
        text = pb.stringForType_("public.utf8-plain-text")
        if text:
            self._launcher_url_field.setStringValue_(text.strip())

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

    # -----------------------------------------------------------------------
    # OCR 翻訳（translategemma:4b via Ollama）
    # -----------------------------------------------------------------------
    # 翻訳ボタン3種: translateJA_ / translateEN_ / translateZH_
    # → _start_translate(lang) → バックグラウンドで _run_translate(text, lang)
    # → 結果を _ocr_result_queue に積む → drainOCRQueue_ で表示

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
        """翻訳をバックグラウンドスレッドで開始する。元テキスト(_ocr_original_text)を使用。"""
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
        """Pinata ストレージと mint サイトを Chrome で左右2分割して開く。"""
        screen_script = 'tell application "Finder" to get bounds of window of desktop'
        result = subprocess.run(["osascript", "-e", screen_script], capture_output=True, text=True)
        try:
            parts = [int(x.strip()) for x in result.stdout.strip().split(",")]
            sw, sh = parts[2], parts[3]
        except Exception:
            sw, sh = 1920, 1080
        hw = sw // 2
        script = "\n".join([
            'tell application "Google Chrome" to activate',
            f'tell application "Google Chrome" to open location "https://sui-mint.torus-studio.tech/"',
            f'tell application "Google Chrome" to set bounds of front window to {{0, 0, {hw}, {sh}}}',
            'tell application "Google Chrome" to make new window',
            f'tell application "Google Chrome" to set URL of active tab of front window to "https://app.pinata.cloud/ipfs/files"',
            f'tell application "Google Chrome" to set bounds of front window to {{{hw}, 0, {sw}, {sh}}}',
        ])
        subprocess.Popen(["osascript", "-e", script])

    @objc.typedSelector(b"v@:@")
    def openStockPages_(self, sender):
        """株情報サイトを Chrome で開き、画面を4分割して均等配置する。"""
        urls = [
            "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtcGhHZ0pLVUNnQVAB?hl=ja&gl=JP&ceid=JP%3Aja",
            "https://kabutan.jp/warning/trading_value_ranking",
            "https://shikiho.toyokeizai.net/ranking",
            "https://www.kabudragon.com/",
        ]
        # 画面サイズ取得
        screen_script = 'tell application "Finder" to get bounds of window of desktop'
        result = subprocess.run(["osascript", "-e", screen_script], capture_output=True, text=True)
        try:
            parts = [int(x.strip()) for x in result.stdout.strip().split(",")]
            sw, sh = parts[2], parts[3]
        except Exception:
            sw, sh = 1920, 1080
        hw, hh = sw // 2, sh // 2
        # 各象限の bounds: {left, top, right, bottom}
        quadrants = [
            (0,   0,   hw,  hh),   # 左上
            (hw,  0,   sw,  hh),   # 右上
            (0,   hh,  hw,  sh),   # 左下
            (hw,  hh,  sw,  sh),   # 右下
        ]
        as_parts = []
        for i, (url, (l, t, r, b)) in enumerate(zip(urls, quadrants)):
            if i == 0:
                as_parts.append(f'tell application "Google Chrome" to activate')
                as_parts.append(f'tell application "Google Chrome" to open location "{url}"')
            else:
                as_parts.append(f'tell application "Google Chrome" to make new window')
                as_parts.append(f'tell application "Google Chrome" to set URL of active tab of front window to "{url}"')
            as_parts.append(f'tell application "Google Chrome" to set bounds of front window to {{{l}, {t}, {r}, {b}}}')
        script = "\n".join(as_parts)
        subprocess.Popen(["osascript", "-e", script])

    @objc.typedSelector(b"v@:@")
    def launchClaudeCode_(self, sender):
        """Terminal を開いて UFO プロジェクトで claude を起動する。"""
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
        """
        Ollama が起動していなければ自動起動し、最大 15 秒待機する。

        起動順:
          1. `open -a Ollama`（Mac アプリ版）を試みる
          2. 失敗した場合 `ollama serve`（CLI 版）を試みる
          3. 1秒ごとにポートを確認し、接続できれば True を返す
          4. 15秒経過しても起動しなければ False を返す
        """
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
        """入力フィールドのテキストを送信する。UFOチャットモード時は nanobot agent へ直接ルーティング。"""
        text = self._msg_field.stringValue().strip()
        if not text:
            return

        self._msg_field.setStringValue_("")
        self._chat_queue.append(("sent", text))  # チャット欄に即時表示

        # UFOと会話モード: nanobot agent -m に直接送信
        if self._ufo_chat_active:
            threading.Thread(target=self._call_nanobot_agent, args=(text,), daemon=True).start()
            return

        # 通常モード: Telegram 送信
        config = tg.load_config()
        if not config:
            self._chat_queue.append((
                "sys",
                "⚠️ Telegram 未設定 — ~/.ufo_config.json を確認してください",
            ))
            self._show_msg_panel()
            return
        token = config.get("telegram_token", "")
        chat_id = str(config.get("telegram_chat_id", ""))
        if not token or not chat_id:
            self._chat_queue.append((
                "sys",
                "⚠️ telegram_token または telegram_chat_id が未設定です",
            ))
            self._show_msg_panel()
            return

        def _send():
            try:
                tg.send_message(token, chat_id, text)
            except Exception as e:
                self._chat_queue.append(("sys", f"⚠️ 送信エラー: {e}"))

        threading.Thread(target=_send, daemon=True).start()

    def _call_nanobot_agent(self, text):
        """nanobot agent -m でワンショット実行し、レスポンスをチャットに流す。"""
        self._run_nanobot_task(text, session_id="desktop:ufo", prefix="🛸", timeout=180)

    def _run_nanobot_task(self, text, *, session_id, prefix, timeout):
        """nanobot agent -m を実行してレスポンスをチャットに流す共通処理。"""
        self._chat_queue.append(("sys", f"{prefix} 考え中…"))
        try:
            env = os.environ.copy()
            env["NO_COLOR"] = "1"   # Rich のカラーコードを無効化
            env["TERM"] = "dumb"
            result = subprocess.run(
                ["uv", "run", "nanobot", "agent", "-m", text, "-s", session_id],
                cwd=NANOBOT_DIR,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
            )
            output = result.stdout.strip()
            # ロゴプレフィックス "🐈 " を除去（複数行の場合も考慮）
            lines = output.splitlines()
            cleaned = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("🐈"):
                    stripped = stripped[1:].lstrip()
                if stripped:
                    cleaned.append(stripped)
            response = "\n".join(cleaned)
            if response:
                self._chat_queue.append(("recv", f"{prefix} {response}"))
            else:
                err = result.stderr.strip()
                msg = err[:300] if err else "（空のレスポンス）"
                self._chat_queue.append(("sys", f"⚠️ {msg}"))
        except subprocess.TimeoutExpired:
            self._chat_queue.append(("sys", f"⚠️ タイムアウト（{timeout}秒）— Ollama が重い可能性があります"))
        except Exception as e:
            self._chat_queue.append(("sys", f"⚠️ エラー: {e}"))

    @objc.typedSelector(b"v@:@")
    def generateAIBriefing_(self, sender):
        """AI情報まとめを Python スクリプトで生成してチャットパネルに表示する。"""
        self._show_msg_panel()
        self._chat_queue.append(("sys", "🤖 AI情報を収集中…"))
        threading.Thread(target=self._run_briefing_script, daemon=True).start()

    def _run_briefing_script(self):
        """briefing.py を直接実行してレスポンスをチャットに流す。LLM不使用・高速。"""
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefing.py")
        try:
            result = subprocess.run(
                ["python3", script],
                capture_output=True,
                text=True,
                timeout=120,  # 翻訳（translategemma:4b）込みで余裕を持たせる
            )
            output = result.stdout.strip()
            if output:
                self._chat_queue.append(("recv", f"🤖 {output}"))
            else:
                err = result.stderr.strip()
                self._chat_queue.append(("sys", f"⚠️ {err[:200] if err else '出力なし'}"))
        except subprocess.TimeoutExpired:
            self._chat_queue.append(("sys", "⚠️ タイムアウト（30秒）— ネットワークを確認してください"))
        except Exception as e:
            self._chat_queue.append(("sys", f"⚠️ エラー: {e}"))

    @objc.typedSelector(b"v@:@")
    def toggleUFOChat_(self, sender):
        """デスクトップから nanobot AI に直接チャットするモードを切り替える。"""
        if self._ufo_chat_active:
            self._ufo_chat_active = False
            self._ufo_chat_item.setTitle_("🛸 UFOと会話")
            self._chat_queue.append(("sys", "🛸 UFOチャット終了"))
        else:
            self._ufo_chat_active = True
            self._ufo_chat_item.setTitle_("🛸 UFO会話中 (停止)")
            self._show_msg_panel()
            self._chat_queue.append(("sys", "🛸 UFOチャット開始 — なんでも聞いてください"))
        self._update_chat_mode()

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
        """
        nanobot ゲートウェイ（~/Desktop/nanobot）を起動する。

        起動手順:
          1. TelegramPoller を停止（Bot トークン競合防止）
          2. nanobot を `uv run nanobot gateway` で起動（失敗時は .venv 直接実行）
          3. プロセスグループ（os.setsid）を使うことで SIGTERM を子プロセスまで伝播
          4. stdout をバックグラウンドスレッドで読み続けてチャットに流す
        """
        if self._is_nanobot_running():
            return

        # nanobot が Bot API の getUpdates を使うため、UFO 側ポーリングと競合する
        # → nanobot 起動前に停止。停止後に _stop_nanobot() で再開する
        self._tg_poller.stop()

        # チャットパネルを表示（nanobot 出力をリアルタイムで確認できるように）
        self._show_msg_panel()

        # uv が PATH にあれば `uv run nanobot gateway`、なければ .venv を直接実行
        try:
            self._nanobot_proc = subprocess.Popen(
                ["uv", "run", "nanobot", "gateway"],
                cwd=NANOBOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,  # プロセスグループを作成（SIGTERM 一括送信用）
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

        # stdout を別スレッドで読み続けてチャットキューに流す
        threading.Thread(
            target=self._read_nanobot_output,
            args=(self._nanobot_proc,),
            daemon=True,
        ).start()

        self._nanobot_item.setTitle_("🐈 nanobot停止")
        self._update_menu_bar_icon()
        self._chat_queue.append(("sys", "🤖 nanobot 起動 — AI が返答します"))
        self._update_chat_mode()

    def _stop_nanobot(self):
        """
        nanobot プロセスを停止して Telegram ポーリングを再開する。

        SIGTERM → 5秒待機 → タイムアウト時 SIGKILL の順で安全に終了させる。
        os.killpg でプロセスグループ全体に送信し、子プロセスも道連れにする。
        """
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

        # nanobot 停止後に UFO 側のポーリングを再開（Telegram 直接受信に戻る）
        self._tg_poller.start()
        self._chat_queue.append(("sys", "📱 nanobot 停止 — Telegram 受信に切り替えました"))
        self._update_chat_mode()

    def _update_chat_mode(self):
        """
        nanobot の稼働状態に合わせてチャットパネルの外観を更新する。

        nanobot 起動中: 緑がかった背景 + AI 案内プレースホルダー
        Telegram のみ:  グレー背景 + 送信案内プレースホルダー
        """
        if not hasattr(self, "_msg_bg"):
            return  # _setup_message_panel 完了前に呼ばれることがあるためガード
        if self._ufo_chat_active:
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.88, 0.93, 1.0, 0.97).CGColor()
            self._msg_field.setPlaceholderString_("🛸 UFOと会話中 — 何でも依頼してください (Enter)")
        elif self._is_nanobot_running():
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.92, 0.97, 0.93, 0.97).CGColor()
            self._msg_field.setPlaceholderString_("🤖 nanobot起動中 — AI が返答します")
        else:
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.96, 0.97, 0.96).CGColor()
            self._msg_field.setPlaceholderString_("Telegramへ送信… (Enter)")
        self._msg_bg.layer().setBackgroundColor_(color)

    def _read_nanobot_output(self, proc):
        """
        nanobot の stdout をバックグラウンドで 1 行ずつ読み続けてチャットキューに積む。
        プロセス終了（EOF）またはエラーで自然終了する。
        """
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._chat_queue.append(("recv", f"🤖 {line}"))
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 自動起動 (Launch Agent)
    # -----------------------------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def toggleBriefingAutostart_(self, sender):
        """ブリーフィング自動実行（毎朝7時）のオン/オフを切り替える。"""
        if autostart.briefing_is_enabled():
            autostart.briefing_disable()
            self._briefing_auto_item.setState_(0)
            self._chat_queue.append(("sys", "⏰ ブリーフィング自動化 OFF"))
        else:
            autostart.briefing_enable(hour=7, minute=0)
            self._briefing_auto_item.setState_(1)
            self._chat_queue.append(("sys", "⏰ ブリーフィング自動化 ON — 毎朝7:00に実行します"))
            self._show_msg_panel()

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

        # デスクトップから nanobot AI に直接チャット
        self._ufo_chat_item = self._make_menu_item("🛸 UFOと会話", "toggleUFOChat:", "", menu)

        # AI情報まとめ（HN・HuggingFace・Arxiv・OpenRouterを巡回してレポート生成）
        self._make_menu_item("🤖 AI情報まとめ", "generateAIBriefing:", "", menu)

        # ブリーフィング自動実行（launchd / 毎朝7時）
        self._briefing_auto_item = self._make_menu_item(
            "⏰ ブリーフィング自動化", "toggleBriefingAutostart:", "", menu
        )
        self._briefing_auto_item.setState_(1 if autostart.briefing_is_enabled() else 0)

        # nanobot ゲートウェイ
        self._nanobot_item = self._make_menu_item("🐈 nanobot起動", "toggleNanobot:", "n", menu)

        # Telegram チャット
        self._msg_panel_item = self._make_menu_item("✉️ Telegram接続", "toggleMsgPanel:", "m", menu)

        # OCR 解析
        self._make_menu_item("🔍 OCR 解析", "startOCR:", "o", menu)

        # NFT 作成
        self._make_menu_item("🎖️ NFT作成", "openNFTPages:", "", menu)

        # 株情報まとめ
        self._make_menu_item("🫜 株情報まとめ", "openStockPages:", "", menu)

        menu.addItem_(NSMenuItem.separatorItem())

        # ショートカット登録
        self._launcher_register_item = self._make_menu_item(
            "✏️ ショートカット登録", "showLauncherPanel:", "", menu
        )
        # 登録済みランチャー（動的）をここに挿入（menu を直接渡す）
        self._rebuild_launcher_menu(menu)

        # チャットクリア
        self._make_menu_item("🧹 チャットクリア", "clearChat:", "", menu)

        menu.addItem_(NSMenuItem.separatorItem())

        # 自動起動（チェックマークで現在状態を表示）
        self._autostart_item = self._make_menu_item(
            "ログイン時に自動起動", "toggleAutostart:", "", menu
        )
        self._autostart_item.setState_(1 if autostart.is_enabled() else 0)

        menu.addItem_(NSMenuItem.separatorItem())

        # 終了
        self._make_menu_item("🗑️ UFOを終了", "quitApp:", "q", menu)

        self._status_item.setMenu_(menu)

    def _make_menu_item(self, title, action, key, menu):
        """NSMenuItem を生成して menu に追加し、返す。"""
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self)
        menu.addItem_(item)
        return item

    def _update_menu_bar_icon(self):
        """
        稼働状態に合わせてメニューバーのドット絵アイコンを切り替える。

        優先度:
          1. チャット受信直後（_chat_flash_ticks > 0）→ mb_chat.png（パイプ付き）
          2. nanobot 起動中                          → mb_active_a/b（点滅アニメ）
          3. 通常                                    → mb_idle.png
        """
        if self._chat_flash_ticks > 0:
            img = self._icon_chat
        elif self._is_nanobot_running():
            # 15tick ごとに a/b を切り替えて点滅させる
            img = self._icon_active_a if (self._icon_tick // 15) % 2 == 0 else self._icon_active_b
        else:
            img = self._icon_idle
        btn = self._status_item.button()
        btn.setTitle_("")   # テキストを消してアイコンのみ表示
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
