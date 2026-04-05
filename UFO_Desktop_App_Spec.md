# UFO Desktop App - 仕様書

## 概要

macOS デスクトップ上にUFOキャラクター画像を常時浮遊表示するアプリケーション。  
将来的にAI連携による画像整理機能を追加予定。段階的に開発を進める。

---

## フェーズ構成

| フェーズ | 内容 | 状態 |
|---------|------|------|
| Phase 1 | UFO浮遊表示（本仕様） | 🔨 開発予定 |
| Phase 2 | インタラクション追加 | 📋 計画中 |
| Phase 3 | Claude API連携・画像整理 | 📋 計画中 |

---

## Phase 1: UFO浮遊表示

### 目的

添付のUFO画像（UFO.png）をデスクトップ上に透明背景で表示し、ふわふわと浮遊するアニメーションをつける。

### 動作環境

- **OS**: macOS 12 (Monterey) 以降
- **Python**: 3.9 以降
- **必須ライブラリ**: PyObjC（`pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz`）
- **ハードウェア**: Apple Silicon / Intel Mac 両対応

### 技術構成

```
ufo-desktop/
├── ufo_app.py          # メインアプリケーション
├── assets/
│   └── UFO.png         # UFO画像（背景透過処理済み）
├── pyproject.toml      # uv プロジェクト設定・依存管理
└── README.md           # セットアップ手順
```

### 機能要件

#### 1. 透明ウィンドウ表示
- NSWindow を `borderless` + `transparent` で生成
- ウィンドウレベルを `NSStatusWindowLevel` に設定（全ウィンドウの上に表示）
- 背景色を完全透明に設定
- マウスイベントを貫通させる（下のウィンドウを操作可能にする）

#### 2. UFO画像の描画
- UFO.png を NSImage として読み込み
- 白背景を透過処理（必要に応じてアルファチャンネル加工）
- 表示サイズ: 約 120×120px（Retina対応）

#### 3. 浮遊アニメーション
- サイン波ベースの上下運動
- 振幅: 10〜15px
- 周期: 約3秒で1往復
- 水平方向の微細な揺れ（振幅: 3〜5px）
- Core Animation（CABasicAnimation）を使用

#### 4. 初期位置
- 画面右下あたりにデフォルト配置
- 将来的にドラッグ移動に対応予定（Phase 2）

#### 5. 終了方法
- メニューバーにアイコン表示（NSStatusItem）
- メニューから「終了」を選択して終了
- `Cmd+Q` でも終了可能

### 非機能要件

- **CPU使用率**: アイドル時 1% 以下
- **メモリ使用量**: 50MB 以下
- **起動時間**: 2秒以内

---

## Phase 2: インタラクション追加（予定）

- ドラッグで自由に移動
- クリック時のリアクション（回転、バウンドなど）
- 右クリックメニューの拡充（設定、移動モード切替など）
- 自動移動モード（画面内をゆっくり巡回）

---

## Phase 3: AI連携・画像整理（予定）

- Claude API と連携
- フォルダをUFOにドラッグ＆ドロップ → 中の画像をAIが分析
- カテゴリ別フォルダに自動仕分け（風景、人物、スクショ、食べ物 等）
- 重複画像の検出
- 「提案 → 確認 → 実行」の3ステップで安全にファイル操作
- Anthropic API キーの設定UI

---

## セットアップ手順（Phase 1）

```bash
# 1. プロジェクト作成
uv init ufo-desktop
cd ufo-desktop

# 2. 依存パッケージを追加
uv add pyobjc-framework-Cocoa pyobjc-framework-Quartz Pillow

# 3. 実行
uv run python ufo_app.py
```

---

## 備考

- UFO.png は元画像の白背景を透過処理して使用する
- Retina ディスプレイでは @2x 相当のサイズで描画される
- 将来的に .app バンドルとしてパッケージング可能（py2app）
