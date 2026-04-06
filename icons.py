"""
icons.py — メニューバー用ピクセルアートアイコン生成

PIL で 18x18 ロジカルピクセル（36x36 物理ピクセル @2x Retina）の
PNG を生成して assets/ に保存する。
"""

import os
from PIL import Image

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

_BLANK = "000000000000000000"

# ---------------------------------------------------------------------------
# UFO ベース（4行上パディングで縦中央寄せ）
# ---------------------------------------------------------------------------

_DOME = [
    "000000011110000000",  # ドーム頂上 (4px)
    "000000111111000000",  # ドーム中段 (6px)
    "000001111111100000",  # ドーム裾   (8px)
]
_BODY = [
    "000011111111110000",  # 円盤 上   (10px)
    "000111111111111000",  # 円盤 中上 (12px)
    "001111111111111100",  # 円盤 最大 (14px)
    "000111111111111000",  # 円盤 中下 (12px)
    "000011111111110000",  # 円盤 下   (10px)
]
_LIGHTS = [
    "000001000100010000",  # ランプ3つ
]

# 4行上パディング + 9行コンテンツ + 5行下 = 18行
_UFO_BASE = [_BLANK] * 4 + _DOME + _BODY + _LIGHTS + [_BLANK] * 5

PATTERN_IDLE = list(_UFO_BASE)


# ---------------------------------------------------------------------------
# nanobot 起動中: UFO + アンダーバー（点滅）
# ---------------------------------------------------------------------------

# フレームA: フルアンダーバー（UFO widest に合わせた 14px）
_BAR_FULL  = "001111111111111100"
# フレームB: 両端の短いティック（点灯中 → 点滅演出）
_BAR_TICKS = "001100000000001100"

# UFO の真下 1行空けてバーを置く
#   rows 0-3 : blank (top pad)
#   rows 4-12: UFO content
#   row  13  : blank gap
#   row  14  : bar
#   rows 15-17: blank
PATTERN_ACTIVE_A = (
    [_BLANK] * 4 + _DOME + _BODY + _LIGHTS
    + [_BLANK, _BAR_FULL]
    + [_BLANK] * 3
)
PATTERN_ACTIVE_B = (
    [_BLANK] * 4 + _DOME + _BODY + _LIGHTS
    + [_BLANK, _BAR_TICKS]
    + [_BLANK] * 3
)


# ---------------------------------------------------------------------------
# チャット受信中: UFO + 両サイド縦線（| UFO |）
# ---------------------------------------------------------------------------

def _with_sidebars(pattern, col_l=0, col_r=17, row_start=4, row_end=12):
    """指定行の左右端に縦線（1px）を追加する。"""
    result = []
    for i, row in enumerate(pattern):
        if row_start <= i <= row_end:
            lst = list(row)
            lst[col_l] = "1"
            lst[col_r] = "1"
            result.append("".join(lst))
        else:
            result.append(row)
    return result

PATTERN_CHAT = _with_sidebars(_UFO_BASE)


# ---------------------------------------------------------------------------
# 描画
# ---------------------------------------------------------------------------

def _render(pattern, path):
    """ピクセルアートを 2x スケール（36x36）の PNG に書き出す。"""
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
    img.save(path)


def generate_all():
    """全アイコンを assets/ に生成する（既存ファイルは上書き）。"""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    _render(PATTERN_IDLE,     os.path.join(ASSETS_DIR, "mb_idle.png"))
    _render(PATTERN_ACTIVE_A, os.path.join(ASSETS_DIR, "mb_active_a.png"))
    _render(PATTERN_ACTIVE_B, os.path.join(ASSETS_DIR, "mb_active_b.png"))
    _render(PATTERN_CHAT,     os.path.join(ASSETS_DIR, "mb_chat.png"))
