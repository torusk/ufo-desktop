"""
telegram.py — Telegram Bot API ユーティリティ

設定ロード・メッセージ送信・受信ポーリングをまとめたモジュール。
AppDelegate から利用する。UI には一切触れない。
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request

# 設定ファイルパス（優先度3番手。詳細は load_config() を参照）
_UFO_CONFIG_PATH = os.path.expanduser("~/.ufo_config.json")
_NANOBOT_CONFIG_PATH = os.path.expanduser("~/.nanobot/config.json")


def load_config():
    """
    Telegram 接続設定をロードして返す。

    優先順:
      1. 環境変数 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
      2. ~/.ufo_config.json  {"telegram_token": "...", "telegram_chat_id": "..."}
      3. ~/.nanobot/config.json  channels.telegram.token / allowFrom[0]

    戻り値: {"telegram_token": str, "telegram_chat_id": str} または None
    """
    # 1. 環境変数
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return {"telegram_token": token, "telegram_chat_id": chat_id}

    # 2. ~/.ufo_config.json（UFO 専用設定）
    try:
        with open(_UFO_CONFIG_PATH) as f:
            cfg = json.load(f)
        if cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
            return cfg
    except Exception:
        pass

    # 3. ~/.nanobot/config.json（nanobot の設定を流用）
    try:
        with open(_NANOBOT_CONFIG_PATH) as f:
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


def send_message(token, chat_id, text):
    """
    sendMessage API を呼び出す（ブロッキング）。
    成功時は何も返さない。失敗時は例外を raise する。
    呼び出し元はバックグラウンドスレッドで実行すること。
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=10)


class TelegramPoller:
    """
    バックグラウンドスレッドで getUpdates をポーリングし、
    新着メッセージを on_message コールバックで通知するクラス。

    注意: nanobot が起動中は stop() で必ず停止すること。
    同じ Bot トークンで 2 プロセスが getUpdates を呼ぶと
    どちらか一方がメッセージを取り損ねる（競合）。
    """

    def __init__(self, on_message):
        """
        on_message: (text: str) -> None
            受信したメッセージテキストを受け取るコールバック。
            バックグラウンドスレッドから呼ばれるため、
            UI 更新はキュー経由で行うこと。
        """
        self._on_message = on_message
        self._active = False
        self._offset = 0  # 既読管理: 次に取得する update_id の下限

    def start(self):
        """ポーリングを開始する。すでに動いている場合は何もしない。"""
        if self._active:
            return
        self._active = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        """ポーリングを停止する（スレッドは次のループで自然終了）。"""
        self._active = False

    # --- 内部メソッド ---

    def _loop(self):
        while self._active:
            config = load_config()
            if config:
                self._fetch(config)
            time.sleep(2)

    def _fetch(self, config):
        """getUpdates を 1 回呼び出して新着を処理する。"""
        token = config.get("telegram_token", "")
        chat_id = str(config.get("telegram_chat_id", ""))
        try:
            url = (
                f"https://api.telegram.org/bot{token}/getUpdates"
                f"?offset={self._offset}&timeout=1&limit=10"
            )
            resp = urllib.request.urlopen(urllib.request.Request(url), timeout=6)
            data = json.loads(resp.read())
            for update in data.get("result", []):
                self._offset = update["update_id"] + 1  # 既読を進める
                msg = update.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) == chat_id:
                    text = msg.get("text", "")
                    if text:
                        self._on_message(text)
        except Exception:
            pass  # ネットワークエラーなどは無視して次のループへ
