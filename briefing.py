#!/usr/bin/env python3
"""AI Daily Briefing — HN + HuggingFace トレンドを取得して markdown に保存する。

依存ライブラリ: なし（標準ライブラリのみ）
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib import request
from xml.etree import ElementTree

HN_RSS_URL  = "https://hnrss.org/frontpage"
HF_API_URL  = "https://huggingface.co/api/models?sort=likes7d&direction=-1&limit=10"
BRIEFINGS_DIR = Path(__file__).parent / "briefings"
HEADERS = {"User-Agent": "UFO-Desktop/1.0"}
TIMEOUT = 15  # 秒


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
    """HuggingFace トレンドモデルを取得する。"""
    data = _fetch(HF_API_URL)
    models = json.loads(data)
    results = []
    for m in models:
        name = m.get("modelId", "")
        task = m.get("pipeline_tag", "")
        if name:
            results.append(f"{name}  ({task})" if task else name)
    return results[:8]


def build_report(hn: list[str], hf: list[str], errors: list[str]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"# 🤖 AI Brief — {today}", ""]

    lines += ["## 🔥 Hacker News", ""]
    lines += [f"- {t}" for t in hn] if hn else ["- (取得失敗)"]
    lines.append("")

    lines += ["## 🤗 HuggingFace トレンド", ""]
    lines += [f"- {m}" for m in hf] if hf else ["- (取得失敗)"]
    lines.append("")

    if errors:
        lines.append(f"⚠️ エラー: {', '.join(errors)}")
        lines.append("")

    lines.append(f"---\n生成: {now}")
    return "\n".join(lines)


def main() -> int:
    errors: list[str] = []

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

    report = build_report(hn, hf, errors)

    BRIEFINGS_DIR.mkdir(exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    out_path = BRIEFINGS_DIR / f"{today}.md"
    out_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n✅ 保存: {out_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
