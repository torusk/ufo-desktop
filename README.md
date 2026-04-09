# UFO Desktop

macOSデスクトップ上にUFOキャラクターをふわふわ浮遊表示するアプリ。
画面上を自律的に飛び回りながら、Telegram チャット・OCR解析・翻訳・ショートカット起動・nanobotゲートウェイ連携・デスクトップAIチャット・AIトレンドブリーフィングなどの機能を持つ。

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

（検討中）

## 主な機能

### 🛸 UFOと会話（デスクトップAIチャット）
- 右クリック「🛸 UFOと会話」でチャットパネルが青みがかった背景で開く
- デスクトップのテキスト入力から直接 nanobot AI に依頼（Telegram不要）
- `nanobot agent -m` をワンショット実行し、レスポンスを 🛸 プレフィックスで表示
- セッション `desktop:ufo` として会話履歴が保持される
- nanobot ゲートウェイ（Telegram）と独立して同時使用可能
- Brave Search API を設定すると Web検索・リアルタイム情報取得が可能

```json
// ~/.nanobot/config.json に追加
{
  "tools": {
    "web": {
      "search": { "apiKey": "YOUR_BRAVE_API_KEY" }
    }
  }
}
```

### 🤖 AI情報まとめ（デイリーブリーフィング）
- 右クリック「🤖 AI情報まとめ」でワンクリック実行、数秒で完了
- **LLM不使用**・標準ライブラリのみ・依存ゼロ（`briefing.py`）
- 以下4ソースを自動巡回してmarkdownレポートを生成：

| ソース | 内容 |
|--------|------|
| [🔥 Hacker News](https://news.ycombinator.com) | テック/AIのホット記事 |
| [🤗 HuggingFace](https://huggingface.co/models?sort=trending) | 週間いいね数トレンドモデル |
| [🔀 OpenRouter](https://openrouter.ai/models) | 新着モデル一覧 |
| [📄 Arxiv cs.AI](https://arxiv.org/list/cs.AI/recent) | 最新AI/ML論文 |

- HN・Arxivタイトルは `translategemma:4b`（Ollama）で自動日本語翻訳
- Ollama未起動時は翻訳をスキップして英語のまま出力
- 生成結果は `briefings/YYYY-MM-DD.md` に保存、各見出しにソースリンク付き

### ⏰ ブリーフィング自動化
- 右クリック「⏰ ブリーフィング自動化」でlaunchd登録（チェックマークで状態表示）
- **毎朝7:00**に `briefing.py` を自動実行
- スリープ中に時刻を過ぎた場合は**次回起動時に自動実行**（cronと違いmissしない）
- ログは `briefings/auto.log` に出力

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

### 🫜 株情報まとめ
- 以下4サイトをワンクリックで Chrome に4分割表示（画面を均等に4象限に配置）
  - 左上: [Google ニュース（経済）](https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtcGhHZ0pLVUNnQVAB?hl=ja&gl=JP&ceid=JP%3Aja)
  - 右上: [世界の株価](https://sekai-kabuka.com/pc-index.html) — 主要指数・為替
  - 左下: [会社四季報オンライン ランキング](https://shikiho.toyokeizai.net/ranking)
  - 右下: [株ドラゴン](https://www.kabudragon.com/)

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
🛸 UFOと会話
🤖 AI情報まとめ
⏰ ブリーフィング自動化
🐈 nanobot起動 / 停止         (N)
✉️ Telegram接続               (M)
🔍 OCR 解析                   (O)
🎖️ NFT作成
🫜 株情報まとめ
────────────────────
✏️ ショートカット登録
🔗 登録したショートカット…
🧹 チャットクリア
────────────────────
ログイン時に自動起動
────────────────────
🗑️ UFOを終了                  (Q)
```

## プロジェクト構成

```
ufo/
├── ufo_app.py          # エントリポイント
├── delegate.py         # AppDelegate（コアロジック・全機能統合）
├── briefing.py         # AIデイリーブリーフィング（LLM不使用・標準ライブラリのみ）
├── views.py            # カスタムUIコンポーネント（UFO・リサイズハンドル等）
├── telegram.py         # Telegram Bot APIユーティリティ
├── autostart.py        # Launch Agent管理
├── icons.py            # メニューバーアイコン生成（ドット絵）
├── assets/
│   ├── UFO.png         # UFO画像（透過PNG）
│   └── mb_*.png        # メニューバーアイコン（自動生成）
├── briefings/          # AIデイリーブリーフィング保存先（YYYY-MM-DD.md）
├── ufocapture/         # スクリーンショット・OCR対象画像の保存先
└── pyproject.toml      # uvプロジェクト設定・依存関係
```

## 依存パッケージ

```
pyobjc-framework-Cocoa   # macOS UIフレームワーク
pyobjc-framework-Quartz  # グラフィックス
Pillow                   # アイコン画像生成
```

Ollama モデル（別途インストール）:
- `glm-ocr` — OCR文字起こし
- `translategemma:4b` — 翻訳・ブリーフィング日本語化

## 動作環境

- macOS 12 (Monterey) 以降（Apple Silicon / Intel 両対応）
- Python 3.9 以降（`uv` で管理）
- [Ollama](https://ollama.com/) — OCR・翻訳機能に必要

