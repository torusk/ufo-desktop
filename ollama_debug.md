# Ollama デバッグ引き継ぎ（2026-04-12）

## 状況
macOS アップデート前に Ollama が全モデルで 500 エラーになっている問題を調査中。
**macOS アップデート後に再確認する。**

## 症状
- Ollama デスクトップ UI（アルパカアイコンのチャットアプリ）でどのモデルを選んでも 500 エラー
- `ollama run qwen3.5 "hi"` などターミナルからも同じエラー
- UFO プロジェクト自体は無関係（UFO は Ollama API を呼ぶだけ）

## 根本原因（特定済み）

```
ggml_metal_device_init: error: failed to create library
ggml_metal_init: the device does not have a precompiled Metal library
GPU family: MTLGPUFamilyApple10 (1010) ← M5
GPU family: MTLGPUFamilyMetal4  (5002)
```

**Ollama 0.20.5 のプリコンパイル済み Metal ライブラリが M5（Apple10 ファミリー）に未対応。**
JIT コンパイルを試みるが macOS 26 上で失敗してクラッシュ（`exit status 2`）。

## 環境
- macOS: 26.3.1 (Build 25D771280a)
- チップ: Apple M5
- Ollama: 0.20.5（Homebrew Cask `ollama-app` でインストール）
- インストール場所: `/Applications/Ollama.app`、バイナリ `/opt/homebrew/bin/ollama`

## 試したこと（効果なし）
- `brew upgrade --cask ollama-app` → すでに最新（0.20.5）だった
- `OLLAMA_NO_METAL=1 ollama run ...` → 同じエラー
- `OLLAMA_FLASH_ATTENTION=0 ollama run ...` → 同じエラー

## 次にやること
1. **macOS アップデート後に `ollama run qwen3.5 "hi"` を試す**
   - 直っていれば → Metal シェーダーコンパイラが修正されたことによる解決
   - まだ壊れていれば → 次の手へ

2. まだ壊れていた場合の workaround 候補：
   - `OLLAMA_NUM_GPU=0 ollama run qwen3.5 "hi"` → CPU 強制（速度は落ちる）
   - Ollama の新バージョン待ち or GitHub Issue #15448, #14432 を確認

## Ollama モデル一覧（参考）
| NAME | SIZE |
|---|---|
| gemma4:latest | 9.6 GB |
| my-qwen:latest | 6.6 GB |
| qwen3.5:latest | 6.6 GB |
| glm-ocr:latest | 2.2 GB |
| translategemma:4b | 3.3 GB |
| translategemma:12b | 8.1 GB |
