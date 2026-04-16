# UFO Desktop

macOSデスクトップ上にUFOキャラクターをふわふわ浮遊表示するアプリ。
画面上を自律的に飛び回りながら、Telegram チャット・OCR解析・翻訳・ショートカット起動・nanobotゲートウェイ連携・デスクトップAIチャット・AIトレンドブリーフィングなどの機能を持つ。

## セットアップ

プロジェクトは `~/ufo` シンボリックリンク経由でアクセスする（実体がどこにあっても同じコマンドで起動できる）。

```bash
cd ~/ufo
uv sync                      # 初回 or 環境を作り直すとき
uv run python ufo_app.py     # 手動起動
```

ログイン時の自動起動はアプリ内メニューの「ログイン時に自動起動」から設定する。
詳細は `docs/startup_guide.md` を参照。

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
├── ufo_app.py          # エントリポイント（起動処理のみ・約25行）
├── delegate.py         # AppDelegate（全機能の司令塔・約1700行）
├── briefing.py         # AIデイリーブリーフィング（LLM不使用・標準ライブラリのみ）
├── views.py            # カスタムUIコンポーネント（UFO・リサイズハンドル等・約190行）
├── telegram.py         # Telegram Bot APIユーティリティ（約135行）
├── autostart.py        # Launch Agent管理（約135行）
├── icons.py            # メニューバーアイコン生成（ドット絵・約115行）
├── assets/
│   ├── UFO.png         # UFO画像（透過PNG）
│   └── mb_*.png        # メニューバーアイコン（自動生成）
├── briefings/          # AIデイリーブリーフィング保存先（YYYY-MM-DD.md）
├── ufocapture/         # スクリーンショット・OCR対象画像の保存先
└── pyproject.toml      # uvプロジェクト設定・依存関係
```

## 機能別コード対応表

手作業で修正したい場合はここを参照してください。

### 🛸 UFO 表示・アニメーション

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| UFO 画像サイズ（120px） | `delegate.py` | L76 `UFO_SIZE = 120` |
| 移動速度・到達判定距離 | `delegate.py` | L78–80 `ROAM_SPEED`, `ARRIVE_THRESHOLD`, `MARGIN` |
| ふわふわの振れ幅・周期 | `delegate.py` | L83–85 `WOBBLE_Y_AMP`, `WOBBLE_X_AMP`, `WOBBLE_PERIOD` |
| アニメーション fps（30fps） | `delegate.py` | L88 `TIMER_INTERVAL` |
| UFO ウィンドウ生成・レベル設定 | `delegate.py` | L237–288 `_setup_ufo_window()` |
| アニメーションループ本体 | `delegate.py` | L306–348 `animationTick_()` |
| シングル/ダブルクリック判定 | `views.py` | L81–111 `ClickableView.mouseDown_()` |
| ドラッグで UFO を移動 | `views.py` | L113–136 `ClickableView.mouseDragged_/mouseUp_()` |
| 右クリック→コンテキストメニュー | `views.py` | L138–141 `ClickableView.rightMouseDown_()` |

### ✉️ Telegram チャットパネル

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| パネルの初期サイズ（280×320px） | `delegate.py` | L91–94 `MSG_PANEL_W/H`, `MSG_CHAT_H`, `MSG_INPUT_H` |
| パネルのレイアウト・ウィジェット生成 | `delegate.py` | L381–498 `_setup_message_panel()` |
| リサイズ時のサブビュー再配置 | `delegate.py` | L513–538 `resize_msg_panel()` |
| メッセージ色（送信=グレー/受信=水色/bot=緑） | `delegate.py` | L574–619 `_refresh_chat_view()` |
| フォントサイズ（12pt 基準） | `delegate.py` | L536 `font_size` 計算式 |
| パネル背景色（モード別） | `delegate.py` | L1574–1583 `_update_chat_mode()` |
| パネルのドラッグ移動 | `views.py` | L41–56 `LogPanelView` |
| パネルの左下リサイズハンドル | `views.py` | L149–190 `ResizeHandleView` |
| Telegram 設定ファイルの読み込み順 | `telegram.py` | L21–59 `load_config()` |
| メッセージ送信（sendMessage API） | `telegram.py` | L62–73 `send_message()` |
| 受信ポーリング間隔（2秒） | `telegram.py` | L110–115 `_loop()` |

### 🤖 AIブリーフィング

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| ブリーフィング本体スクリプト | `briefing.py` | ファイル全体 |
| 実行タイムアウト（120秒） | `delegate.py` | L1450 `timeout=120` |
| 実行・チャット表示トリガー | `delegate.py` | L1436–1461 `generateAIBriefing_()`, `_run_briefing_script()` |

### ⏰ ブリーフィング自動化（launchd）

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| 実行時刻（毎朝7:00） | `delegate.py` | L1610 `autostart.briefing_enable(hour=7, minute=0)` |
| plist 生成・登録・解除 | `autostart.py` | L83–133 `briefing_enable()`, `briefing_disable()` |
| ログ出力先（`briefings/auto.log`） | `autostart.py` | L80 `_BRIEFING_LOG` |

### 🔍 OCR 解析

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| OCR パネルのサイズ（300×270px） | `delegate.py` | L96–99 `OCR_PANEL_W/H`, `OCR_PAD`, `OCR_BTN_H` |
| OCR パネルのレイアウト生成 | `delegate.py` | L659–761 `_setup_ocr_panel()` |
| OCR 実行（glm-ocr 呼び出し） | `delegate.py` | L1314–1346 `_run_ocr()` |
| Ollama 自動起動（最大15秒待機） | `delegate.py` | L1280–1312 `_ensure_ollama_running()` |
| 翻訳ボタン（translategemma:4b） | `delegate.py` | L1149–1177 `_run_translate()` |
| 翻訳プロンプト文 | `delegate.py` | L1158 `prompt =` の行 |

### ✏️ ショートカット登録

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| パネルのサイズ（360×260px） | `delegate.py` | L101–106 `LAUNCHER_PANEL_W/H`, `LAUNCHER_PAD`, `LAUNCHER_ROW_H` |
| パネルのレイアウト生成 | `delegate.py` | L861–968 `_setup_launcher_panel()` |
| 登録データの保存先（`~/.ufo_config.json`） | `delegate.py` | L109 `CONFIG_PATH` |
| 設定の読み込み・保存 | `delegate.py` | L834–859 `_load_launchers()`, `_save_launchers()` |
| メニューへの動的追加 | `delegate.py` | L1021–1043 `_rebuild_launcher_menu()` |

### 🐈 nanobot ゲートウェイ

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| nanobot のディレクトリ（`~/Desktop/nanobot`） | `delegate.py` | L72 `NANOBOT_DIR` |
| 起動コマンド（`uv run nanobot gateway`） | `delegate.py` | L1512–1528 `_start_nanobot()` |
| 停止（SIGTERM→5秒→SIGKILL） | `delegate.py` | L1542–1563 `_stop_nanobot()` |
| stdout をチャットへ流す | `delegate.py` | L1585–1596 `_read_nanobot_output()` |

### 🛸 UFOと会話（デスクトップ AI チャット）

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| nanobot agent 呼び出し | `delegate.py` | L1394–1433 `_call_nanobot_agent()`, `_run_nanobot_task()` |
| セッションID（`desktop:ufo`） | `delegate.py` | L1396 `session_id="desktop:ufo"` |
| タイムアウト（180秒） | `delegate.py` | L1396 `timeout=180` |
| モード切り替えトリガー | `delegate.py` | L1463–1475 `toggleUFOChat_()` |

### 🫜 株情報まとめ / 🎖️ NFT作成

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| 株情報の4つの URL と配置 | `delegate.py` | L1230–1263 `openStockPages_()` |
| NFT の2つの URL と配置 | `delegate.py` | L1208–1226 `openNFTPages_()` |

### ⚡️ Claude Code 起動

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| 起動コマンド（`cd ... && claude`） | `delegate.py` | L1265–1270 `launchClaudeCode_()` |

### メニューバー

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| メニュー項目の追加・並び順・ショートカットキー | `delegate.py` | L1628–1702 `_setup_menu_bar()` |
| アイコンの切り替えロジック（通常/nanobot/チャット受信） | `delegate.py` | L1704–1722 `_update_menu_bar_icon()` |
| アイコンのピクセルアートデザイン | `icons.py` | L13–85（各パターン定数） |
| アイコン画像の生成・保存 | `icons.py` | L107–113 `generate_all()` |

### ログイン時自動起動

| 修正したい内容 | ファイル | 場所 |
|---|---|---|
| plist の識別子・保存先 | `autostart.py` | L13–14 `LABEL`, `PLIST_PATH` |
| plist 生成・launchctl 登録 | `autostart.py` | L25–63 `enable()` |
| 自動起動の無効化 | `autostart.py` | L66–70 `disable()` |

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

