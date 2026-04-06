"""
icons.py — メニューバー用ピクセルアートアイコン生成

PIL で 18x18 ロジカルピクセル（36x36 物理ピクセル @2x Retina）の
PNG を生成して assets/ に保存する。
"""

import os
from PIL import Image

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# ---- ピクセルアート定義 ('1'=黒, '0'=透明, 18列 x 18行) ----

_DOME = [
    "000000011110000000",  # ドーム頂上 (4px)
    "000000111111000000",  # ドーム中段 (6px)
    "000001111111100000",  # ドーム裾   (8px)
]

_BODY = [
    "000011111111110000",  # 円盤 上    (10px)
    "000111111111111000",  # 円盤 中上  (12px)
    "001111111111111100",  # 円盤 最大  (14px)
    "000111111111111000",  # 円盤 中下  (12px)
    "000011111111110000",  # 円盤 下    (10px)
]

# 待機: 下部に小さなランプ3つ
_LIGHTS_IDLE = [
    "000001000100010000",
]

# ビーム A（幅広）: nanobot 起動中フレーム1
_BEAM_A = [
    "000001111111100000",
    "000000111111000000",
    "000000011110000000",
]

# ビーム B（幅狭）: nanobot 起動中フレーム2
_BEAM_B = [
    "000000111111000000",
    "000000011110000000",
    "000000001100000000",
]

_BLANK = "000000000000000000"


def _pad(rows, total=18):
    result = list(rows)
    while len(result) < total:
        result.append(_BLANK)
    return result[:total]


# 各状態のパターン
PATTERN_IDLE     = _pad(_DOME + _BODY + _LIGHTS_IDLE)
PATTERN_ACTIVE_A = _pad(_DOME + _BODY + _BEAM_A)
PATTERN_ACTIVE_B = _pad(_DOME + _BODY + _BEAM_B)


def _render(pattern, path, dot=False):
    """
    ピクセルアートを 2x スケール（36x36）の PNG に書き出す。
    dot=True のとき右上に通知ドットを追加する。
    """
    scale = 2
    size = 18
    img = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    pixels = img.load()
    for y, row in enumerate(pattern):
        for x, ch in enumerate(row):
            if ch == "1":
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[x * scale + dx, y * scale + dy] = (0, 0, 0, 255)
    if dot:
        # 右上 4x4 の通知ドット
        for dy in range(4):
            for dx in range(4):
                pixels[32 + dx, dy] = (0, 0, 0, 255)
    img.save(path)


def generate_all():
    """全アイコンを assets/ に生成する（既存ファイルは上書き）。"""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    _render(PATTERN_IDLE,     os.path.join(ASSETS_DIR, "mb_idle.png"))
    _render(PATTERN_ACTIVE_A, os.path.join(ASSETS_DIR, "mb_active_a.png"))
    _render(PATTERN_ACTIVE_B, os.path.join(ASSETS_DIR, "mb_active_b.png"))
    _render(PATTERN_IDLE,     os.path.join(ASSETS_DIR, "mb_chat.png"), dot=True)
