#!/usr/bin/env python3
"""AI Daily Briefing — HN + HuggingFace + OpenRouter を取得し日本語で保存する。

依存ライブラリ: なし（標準ライブラリのみ）
翻訳: Ollama translategemma:4b（ローカル、起動していない場合はスキップ）
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib import request
from xml.etree import ElementTree

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
HN_RSS_URL  = "https://hnrss.org/frontpage"
HF_API_URL  = "https://huggingface.co/api/models?sort=likes7d&direction=-1&limit=10"
OR_API_URL  = "https://openrouter.ai/api/v1/models"
OLLAMA_URL  = "http://localhost:11434/api/generate"
TRANSLATE_MODEL = "translategemma:4b"

BRIEFINGS_DIR = Path(__file__).parent / "briefings"
HEADERS  = {"User-Agent": "UFO-Desktop/1.0"}
TIMEOUT  = 15   # HTTP fetch タイムアウト（秒）
TL_TIMEOUT = 90  # 翻訳タイムアウト（秒）


# ---------------------------------------------------------------------------
# データ取得
# ---------------------------------------------------------------------------

def _fetch(url: str) -> bytes:
    req = request.Request(url, headers=HEADERS)
    with request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_hn() -> list[str]:
    """Hacker News フロントページから記事タイトルを取得する。"""
    data = _fetch(HN_RSS_URL)
    root = ElementTree.fromstring(data)
    titles = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if title:
            titles.append(title)
    return titles[:8]


def fetch_hf() -> list[str]:
    """HuggingFace 週間いいね数トレンドモデルを取得する。"""
    data = _fetch(HF_API_URL)
    models = json.loads(data)
    results = []
    for m in models:
        name = m.get("modelId", "")
        task = m.get("pipeline_tag", "")
        if name:
            results.append(f"{name}  ({task})" if task else name)
    return results[:8]


def fetch_openrouter() -> list[str]:
    """OpenRouter 公開モデルリスト上位を取得する（認証不要）。"""
    data = _fetch(OR_API_URL)
    result = json.loads(data)
    seen: set[str] = set()
    names: list[str] = []
    for m in result.get("data", []):
        mid = m.get("id", "")
        # :free バリアントは重複になるので除外
        if not mid or mid.endswith(":free"):
            continue
        base = mid.split(":")[0]
        if base not in seen:
            seen.add(base)
            names.append(mid)
        if len(names) >= 8:
            break
    return names


# ---------------------------------------------------------------------------
# 翻訳（Ollama / translategemma:4b）
# ---------------------------------------------------------------------------

def translate(text: str) -> str:
    """テキストを translategemma:4b で日本語翻訳する。失敗時は原文を返す。"""
    prompt = (
        "Translate the following to Japanese. "
        "Keep model names (e.g. 'google/gemma', 'anthropic/claude', 'qwen/'), "
        "URLs, and code exactly as-is:\n\n" + text
    )
    payload = json.dumps({
        "model": TRANSLATE_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode()
    req = request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=TL_TIMEOUT) as resp:
        return json.loads(resp.read()).get("response", "").strip()


def translate_items(items: list[str]) -> list[str]:
    """リストをまとめて翻訳する。失敗時は原文リストを返す。"""
    if not items:
        return items
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
    try:
        result = translate(numbered)
        translated = []
        for line in result.splitlines():
            line = line.strip()
            # "1. ..." の番号プレフィックスを除去
            if line and line[0].isdigit() and ". " in line:
                line = line.split(". ", 1)[1]
            if line:
                translated.append(line)
        # 件数が合わなければ原文にフォールバック
        if len(translated) == len(items):
            return translated
    except Exception:
        pass
    return items


# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------

def build_report(
    hn: list[str],
    hf: list[str],
    or_: list[str],
    errors: list[str],
    translated: bool,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")
    tl_note = "（translategemma:4b で日本語化）" if translated else "（翻訳スキップ — Ollama未起動？）"

    lines = [f"# 🤖 AI Brief — {today}", ""]

    lines += ["## 🔥 Hacker News", ""]
    lines += [f"- {t}" for t in hn] if hn else ["- (取得失敗)"]
    lines.append("")

    lines += ["## 🤗 HuggingFace トレンド（週間）", ""]
    lines += [f"- {m}" for m in hf] if hf else ["- (取得失敗)"]
    lines.append("")

    lines += ["## 🔀 OpenRouter 新着モデル", ""]
    lines += [f"- {m}" for m in or_] if or_ else ["- (取得失敗)"]
    lines.append("")

    if errors:
        lines.append(f"⚠️ エラー: {', '.join(errors)}")
        lines.append("")

    lines.append(f"---\n生成: {now}  {tl_note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> int:
    errors: list[str] = []

    # --- データ取得 ---
    try:
        hn = fetch_hn()
    except Exception as e:
        hn = []
        errors.append(f"HN: {e}")

    try:
        hf = fetch_hf()
    except Exception as e:
        hf = []
        errors.append(f"HF: {e}")

    try:
        or_ = fetch_openrouter()
    except Exception as e:
        or_ = []
        errors.append(f"OR: {e}")

    # --- HN タイトルを日本語翻訳 ---
    translated = False
    if hn:
        hn_ja = translate_items(hn)
        if hn_ja is not hn:   # 翻訳成功（新リストが返ってきた）
            hn = hn_ja
            translated = True

    # --- レポート生成 ---
    report = build_report(hn, hf, or_, errors, translated)

    # --- 保存 ---
    BRIEFINGS_DIR.mkdir(exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    out_path = BRIEFINGS_DIR / f"{today}.md"
    out_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n✅ 保存: {out_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
