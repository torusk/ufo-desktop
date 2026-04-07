# UFO Desktop

macOSデスクトップ上にUFOキャラクターをふわふわ浮遊表示するアプリ。
画面上を自律的に飛び回りながら、Telegram チャット・OCR解析・翻訳・ショートカット起動・nanobotゲートウェイ連携などの機能を持つ。

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
| 停止中にドラッグ | UFO を任意の位置へ移動 |
| 右クリック | コンテキストメニュー |
| メニューバー 🛸 | 各種操作メニュー |

### メニューバーアイコンの状態

| アイコン | 状態 |
|----------|------|
| 🛸（通常） | UFO浮遊中 |
| 🛸💤 | UFO停止中 |
| バー点滅 | nanobot実行中 |
| パイプ表示 | Telegramメッセージ受信中 |

## 主な機能

### ✉️ Telegram接続（チャットパネル）
- 画面右上に固定表示（ドラッグで任意の場所に移動可能）
- スマホからの Telegram メッセージを受信・送信（LINE風の左右配置）
  - 送信: 右寄せ・グレーバブル
  - 受信: 左寄せ・水色バブル
- **左下コーナーをドラッグ**してパネルサイズを自由に変更（文字サイズも比例して拡大）
- Ollama モデル設定（`~/.ufo_config.json` または `~/.nanobot/config.json`）

```json
{
  "telegram_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

#### nanobot 連携時の動作
- 🐈 nanobot起動中は Telegram ポーリングを停止し、nanobot が Telegram を処理
- nanobot からの AI 応答は **緑バブル・🤖 プレフィックス** で表示
- 起動/停止時にシステムメッセージをチャットに挿入
- パネル背景色で現在モードを視覚的に区別（Telegram のみ: グレー / nanobot 起動中: 緑）

### 🔍 OCR解析
- 右クリックまたはメニューバーから起動
- 画像（PNG/JPG）を選択して `glm-ocr`（Ollama経由）でテキストを文字起こし
- 結果パネルで **翻訳ボタン**（日本語 / English / 中文）を押すと `translategemma:4b` で翻訳
- コピーボタンでクリップボードに転送
- Ollama 未起動の場合は自動起動を試みる（最大15秒待機）

### ✏️ ショートカット登録
- 右クリックまたはメニューバーから「✏️ ショートカット登録」でパネルを表示
- **名前 + URL** を登録するとメニューに 🔗 項目として追加、クリックでブラウザ起動
- 📋 ボタンでクリップボードの URL を貼り付け
- × ボタンで削除
- 登録データは `~/.ufo_config.json` の `launchers` キーに保存

### 🐈 nanobotゲートウェイ連携
- メニューバーから「🐈 nanobot起動/停止」で制御
- 実行中はメニューバーアイコンがアニメーション表示
- nanobot の出力は Telegram チャットパネルにリアルタイム表示（🤖 付き）

### 🎖️ NFT作成
- Pinata ストレージと mint サイトをブラウザで開く

### ⚡️ Claude Code起動
- Terminal を開いて UFO プロジェクトディレクトリで `claude` を起動

### ログイン時自動起動
- macOS Launch Agent として登録可能（メニューバーから設定）

## メニュー構成

```
UFO を隠す                    (U)
────────────────────
⚡️ claude code起動            (C)
🐈 nanobot起動 / 停止         (N)
✉️ Telegram接続               (M)
🔍 OCR 解析                   (O)
🎖️ NFT作成
────────────────────
✏️ ショートカット登録
🔗 登録したショートカット…
────────────────────
🧹 チャットクリア
────────────────────
ログイン時に自動起動
```

## プロジェクト構成

```
ufo/
├── ufo_app.py          # エントリポイント
├── delegate.py         # AppDelegate（コアロジック・全機能統合）
├── views.py            # カスタムUIコンポーネント（UFO・リサイズハンドル等）
├── telegram.py         # Telegram Bot APIユーティリティ
├── autostart.py        # Launch Agent管理
├── icons.py            # メニューバーアイコン生成（ドット絵）
├── assets/
│   ├── UFO.png         # UFO画像（透過PNG）
│   └── mb_*.png        # メニューバーアイコン（自動生成）
├── ufocapture/         # スクリーンショット・OCR対象画像の保存先
└── pyproject.toml      # uvプロジェクト設定・依存関係
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
- [Ollama](https://ollama.com/) — OCR・翻訳機能に必要（`glm-ocr`・`translategemma:4b` モデル）

## 開発ロードマップ

| フェーズ | 内容 | 状態 |
|----------|------|------|
| Phase 1 | UFO浮遊表示・サイン波アニメーション | ✅ 完了 |
| Phase 2 | インタラクティブ操作・Telegram・OCR・翻訳・nanobot・ショートカット登録 | ✅ 完了 |
| Phase 3 | Claude API連携（フォルダD&D画像分類・重複検出） | 📋 計画中 |
