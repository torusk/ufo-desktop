# UFO Desktop

macOSデスクトップ上にUFOキャラクターをふわふわ浮遊表示するアプリ。
画面上を自律的に飛び回りながら、Telegram通知・OCR解析・nanobotゲートウェイ連携などの機能を持つ。

## セットアップ

```bash
uv sync
uv run python ufo_app.py
```

## 操作方法

| 操作 | 動作 |
|------|------|
| シングルクリック | 浮遊の停止 / 再開 |
| ダブルクリック | 範囲選択スクリーンショット起動（`ufocapture/` に保存） |
| 停止中にドラッグ | UFO・メッセージパネルを任意の位置へ移動 |
| 右クリック | コンテキストメニュー（OCR解析など） |
| メニューバー 🛸 | 各種操作メニュー |

### メニューバーアイコンの状態

| アイコン | 状態 |
|----------|------|
| 🛸（通常） | UFO浮遊中 |
| 🛸💤 | UFO停止中 |
| バー点滅 | nanobot実行中 |
| パイプ表示 | Telegramメッセージ受信中 |

## 主な機能

### Telegram連携
- Telegram Botを通じてメッセージを受信し、UFOの吹き出しに表示・返信可能
- 設定は `~/.ufo_config.json` または `~/.nanobot/config.json` で管理

```json
{
  "telegram_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

### OCR解析
- 右クリックメニューまたはメニューバーから「🔍 OCR 解析」を選択
- ファイル選択ダイアログで画像（PNG/JPG）を指定
- `glm-ocr`（Ollama経由）でテキストを文字起こし
- 結果をパネル表示・クリップボードコピー可能
- Ollama未起動の場合は自動起動を試みる（最大15秒待機）

### nanobotゲートウェイ連携
- メニューバーから「🐈 nanobot起動/停止」で制御
- 実行中はメニューバーアイコンがアニメーション表示
- nanobot起動中はTelegramポーリングを一時停止（競合回避）
- nanobot の stdout はログパネルにリアルタイム表示

### NFT作成
- メニューバーから「🎖️ NFT作成」でPinataストレージとmintサイトをブラウザで開く

### Claude Code起動
- メニューバーから「⚡️ claude code起動」でTerminalを開きUFOプロジェクトディレクトリで `claude` を起動

### ログイン時自動起動
- macOS Launch Agentとして登録可能（メニューバーから設定）

## プロジェクト構成

```
ufo/
├── ufo_app.py          # エントリポイント
├── delegate.py         # AppDelegate（コアロジック・全機能統合）
├── views.py            # カスタムUIコンポーネント（UFOウィンドウ・クリック処理）
├── telegram.py         # Telegram Bot APIユーティリティ
├── autostart.py        # Launch Agent管理
├── icons.py            # メニューバーアイコン生成（ドット絵）
├── assets/
│   ├── UFO.png         # UFO画像（透過PNG）
│   └── mb_*.png        # メニューバーアイコン（自動生成）
├── ufocapture/         # スクリーンショット・OCR対象画像の保存先
├── pyproject.toml      # uvプロジェクト設定・依存関係
└── UFO_Desktop_App_Spec.md  # 詳細仕様書
```

## 依存パッケージ

```
pyobjc-framework-Cocoa   # macOS UIフレームワーク
pyobjc-framework-Quartz  # グラフィックス
Pillow                   # アイコン画像生成
```

## 動作環境

- macOS 12 (Monterey) 以降（Apple Silicon / Intel 両対応）
- Python 3.9 以降（`uv` で管理）
- [Ollama](https://ollama.com/) — OCR機能利用時に必要（`glm-ocr` モデル）

## 開発ロードマップ

| フェーズ | 内容 | 状態 |
|----------|------|------|
| Phase 1 | UFO浮遊表示・サイン波アニメーション | ✅ 完了 |
| Phase 2 | インタラクティブ操作・Telegram・OCR・nanobot連携 | ✅ 完了 |
| Phase 3 | Claude API連携（フォルダD&D画像分類・重複検出） | 📋 計画中 |
