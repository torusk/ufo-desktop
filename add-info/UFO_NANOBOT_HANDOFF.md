# UFO × nanobot 統合プロジェクト 連絡資料

## 概要

デスクトップを漂うUFOアプリに、nanobotを統合してAI搭載のデスクトップ常駐アシスタントにするプロジェクト。
現時点ではメニューバーからのnanobot起動/停止機能を追加済み。今後Telegram連携やイベント駆動のモーション変更などを検討中。

---

## 現在の環境

- **マシン**: MacBook Pro（Apple Silicon, 24GB RAM）
- **ローカルLLM**: Ollama（qwen2.5:14b をメイン利用、gemma2:9b / llama3.2:3b も選択肢）
- **nanobot**: HKUDS/nanobot のフォーク → `torusk/nanobot-for-mbp`（プライベート推奨）
- **Telegram bot**: 設定済み（BotFather発行トークン + User ID制限で運用）
- **UFOアプリ**: PyObjC製、メニューバー常駐、デスクトップ上をふわふわ移動

---

## リポジトリ構成

### UFOアプリ（ufo_app.py + assets/UFO.png）

起動: `uv run python ufo_app.py`

### nanobot（~/Desktop/nanobot）

リポジトリ: https://github.com/torusk/nanobot-for-mbp（現在public、プライベートに戻す予定）

オリジナルのHKUDS/nanobotに対して以下の独自修正あり:

1. **モデル名重複回避** - 通信ライブラリが `hosted_vllm/` 等の接頭辞を付ける問題を修正
2. **本人確認ロジック改善** - Username → 数字IDで認証するように変更
3. **レスポンスクリーニング** - AIが出力するJSONノイズを除去

追加ドキュメント:
- `PROJECT_LOG.md` - 2026/02/02のセットアップ記録
- `LOCAL_USAGE.md` - 日常の起動方法、権限、セキュリティガイド
- `NANOBOT_PROPOSAL.md` - 軽量モデル選定と活用シナリオ

nanobot設定ファイル: `~/.nanobot/config.json`

---

## 今回の変更内容（ufo_app.py）

### メニューバーの拡張

**変更前:**
- 🛸 アイコン + 「終了」のみ

**変更後:**
- 🛸💤（nanobot停止中）/ 🛸（起動中）でステータス表示
- 「nanobot 起動」/「nanobot 停止」トグルメニュー（⌘N）
- 「終了」（⌘Q）- nanobot も自動停止してから終了

### nanobot gateway プロセス管理

- `uv run nanobot gateway` で起動、uvが無ければ `.venv/bin/nanobot` にフォールバック
- `preexec_fn=os.setsid` でプロセスグループ生成 → 停止時に子プロセスごとクリーンに終了
- `applicationWillTerminate_` でアプリ終了時も自動停止

### 要確認箇所

- `NANOBOT_DIR`（55行目）: `~/Desktop/nanobot` になっている。パスが違う場合は修正が必要

---

## 今後の検討事項

### 1. Telegram → UFO モーション連携

nanobotのメッセージバス（`bus/`）経由でTelegramからのコマンドをUFOアプリに伝える仕組み。

想定コマンド例:
- 「踊れ」→ 特殊モーション（高速旋回、ジグザグ等）
- 「消えろ」→ フェードアウトして休止
- 「クリップボード読んで」→ 内容をAIで要約してTelegramに返す
- 「今日のスケジュール」→ UFOがふきだし表示

実装アプローチ: nanobotとUFOアプリ間をローカルのUnixソケットまたはHTTP（localhost）で接続。nanobotのskillとしてUFO制御コマンドを登録する形が自然。

### 2. macOS通知連携（優先度低め）

macOSの通知を監視してUFOの飛び方を変える案。`NSDistributedNotificationCenter` や `NSWorkspace` の通知監視で技術的には可能だが、無理にやる必要はない。

### 3. cronジョブ連携

nanobotの `nanobot cron add` で定期タスクを設定し、結果をUFOのふきだしで表示。
例: 毎朝9時にUFOが天気を教えてくれる。

### 4. LLMの選択

現在使用可能なモデル（2026-04-05時点、`ollama list` より）:

| モデル | サイズ | 用途 |
|---|---|---|
| gemma4:latest | 9.6GB | 最新Gemma。メイン候補 |
| my-qwen:latest | 6.6GB | カスタムQwenモデル |
| qwen3.5:latest | 6.6GB | Qwen 3.5。バランス型 |
| glm-ocr:latest | 2.2GB | OCR特化 |
| translategemma:4b | 3.3GB | 翻訳特化（軽量） |
| translategemma:12b | 8.1GB | 翻訳特化（高精度） |

OpenRouter経由でクラウドLLM（Claude Sonnet等）も切り替え可能。ローカルLLMの推論速度を考慮して、UFOのリアクションは非同期（考え中モーション → 結果表示）にするのが現実的。

---

## セキュリティ注意事項

- **Bot Token**: 流出厳禁。漏れた場合は `@BotFather` で `/revoke` して即無効化
- **User ID制限**: `config.json` の `allowFrom` で自分のIDのみ許可
- **リポジトリ**: `LOCAL_USAGE.md` にMacユーザー名パスやbot名が含まれるため、プライベートに戻すことを推奨
- **物理スイッチ**: ターミナルで Ctrl+C、またはメニューバーから「終了」で全停止
