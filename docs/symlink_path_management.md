# プロジェクトのパス管理 — シンボリックリンク方式

プロジェクトを別フォルダに移動するたびにパスを書き換えるのを避けるため、
ホームディレクトリに固定シンボリックリンクを置き、LaunchAgents等はそこを参照する設計にしている。

## 現在の構成

```
~/ufo      → 実際の ufo プロジェクト（現在: ~/Desktop/ufo）
~/nanobot  → 実際の nanobot プロジェクト（現在: ~/Desktop/nanobot）
```

LaunchAgents やツール設定は `/Users/kazuki/ufo` / `/Users/kazuki/nanobot` を参照している。
物理的な場所が変わっても、シンボリックリンクを更新するだけでよい。

## パスを参照しているファイル一覧

| ファイル | 参照パス |
|---|---|
| `~/Library/LaunchAgents/com.ufo.briefing.plist` | `/Users/kazuki/ufo/` |
| `~/Library/LaunchAgents/com.ufo.desktop.plist` | `/Users/kazuki/ufo/` |
| `ufo/.claude/settings.local.json` | `/Users/kazuki/ufo/`、`/Users/kazuki/nanobot/` |
| `nanobot/LOCAL_USAGE.md` | 移動先パスをドキュメント内に記載（実害なし） |

## プロジェクトを移動するときの手順

### 1. LaunchAgent を止める

```bash
launchctl unload ~/Library/LaunchAgents/com.ufo.briefing.plist
launchctl unload ~/Library/LaunchAgents/com.ufo.desktop.plist
```

### 2. フォルダを移動する

```bash
# 例: ufo を 202604 フォルダへ移動
mv ~/Desktop/ufo ~/Documents/2026作成物等/202604/ufo

# 例: nanobot を 202602 フォルダへ移動
mv ~/Desktop/nanobot ~/Documents/2026作成物等/202602/nanobot
```

### 3. シンボリックリンクを更新する（これだけでOK）

```bash
ln -sfn ~/Documents/2026作成物等/202604/ufo ~/ufo
ln -sfn ~/Documents/2026作成物等/202602/nanobot ~/nanobot
```

> `-sfn` オプションで、既存のシンボリックリンクを上書き更新できる。

### 4. .venv を再構築する

`.venv` 内部にはパスが焼き込まれているが、シンボリックリンク経由であれば
パスが変わらないため **再構築不要**。
（直接 mv した場合のみ `uv sync` が必要）

### 5. LaunchAgent を再ロードする

```bash
launchctl load ~/Library/LaunchAgents/com.ufo.briefing.plist
launchctl load ~/Library/LaunchAgents/com.ufo.desktop.plist
```

### 6. 動作確認

```bash
ls -la ~/ufo       # シンボリックリンク先が正しいか確認
ls -la ~/nanobot   # 同上
```

## 初期セットアップ（シンボリックリンクを作り直す場合）

```bash
ln -sfn /実際のパス/ufo /Users/kazuki/ufo
ln -sfn /実際のパス/nanobot /Users/kazuki/nanobot
```

## 注意点

- `~/ufo` と `~/nanobot` はシンボリックリンクなので、**削除しても実体は消えない**（`rm ~/ufo` はリンクだけ消える）
- `rm -rf ~/ufo/` のように末尾に `/` をつけると**実体が消えるので注意**
- Claude Code で作業するときは `~/ufo` から開けば、移動後もパスが安定する
