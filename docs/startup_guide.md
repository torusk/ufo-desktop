# UFO Desktop — 起動ガイド

## プロジェクトのパスについて

プロジェクトは `~/ufo` シンボリックリンク経由でアクセスする。
実体が別フォルダに移動しても、このシンボリックリンクは変わらない。

```
~/ufo  →  実体（例: ~/Documents/2026作成物等/202604/ufo）
```

---

## 起動方法

### A. 手動起動（開発・デバッグ時）

```bash
cd ~/ufo
uv run python ufo_app.py
```

### B. ログイン時の自動起動（LaunchAgent）

アプリを一度起動した後、右クリックメニュー or メニューバーから
**「ログイン時に自動起動」** をオンにする。

これにより `~/Library/LaunchAgents/com.ufo.desktop.plist` が自動生成・登録される。
手動で制御したい場合:

```bash
# 登録（自動起動オン）
launchctl load ~/Library/LaunchAgents/com.ufo.desktop.plist

# 解除（自動起動オフ）
launchctl unload ~/Library/LaunchAgents/com.ufo.desktop.plist
```

### C. Claude Code で開発作業

```bash
cd ~/ufo
claude
```

---

## ブリーフィング自動化（毎朝7:00）

右クリック「⏰ ブリーフィング自動化」でオン/オフを切り替える。

手動でコマンド実行する場合:

```bash
cd ~/ufo
uv run python briefing.py
```

---

## 依存パッケージのインストール（初回 or 環境を作り直すとき）

```bash
cd ~/ufo
uv sync
```

---

## プロジェクトを別フォルダに移動するとき

`docs/symlink_path_management.md` を参照。
シンボリックリンクを更新するだけで、他のファイルは変更不要。

```bash
launchctl unload ~/Library/LaunchAgents/com.ufo.briefing.plist
launchctl unload ~/Library/LaunchAgents/com.ufo.desktop.plist

mv ~/ufo の実体 /新しい場所

ln -sfn /新しい場所/ufo ~/ufo

launchctl load ~/Library/LaunchAgents/com.ufo.briefing.plist
launchctl load ~/Library/LaunchAgents/com.ufo.desktop.plist
```
