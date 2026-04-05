# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

macOS desktop app that displays a floating UFO character (UFO.png) with transparent background. Planned in three phases:

- **Phase 1** (current): UFO floating display with sine-wave animation
- **Phase 2**: Interactivity (drag-to-move, click reactions, auto-roaming)
- **Phase 3**: Claude API integration for drag-and-drop image classification and duplicate detection

## Setup & Running

```bash
# Initialize project
uv init ufo-desktop
cd ufo-desktop

# Install dependencies
uv add pyobjc-framework-Cocoa pyobjc-framework-Quartz Pillow

# Run
uv run python ufo_app.py
```

## Planned Project Structure

```
ufo-desktop/
├── ufo_app.py          # Main application entry point
├── assets/
│   └── UFO.png         # UFO image (transparent background)
├── pyproject.toml      # uv project config and dependencies
└── README.md
```

## Architecture

### Phase 1 Core Components

- **NSWindow** — Borderless + transparent, set to `NSStatusWindowLevel` (floats above all windows), mouse events pass through to underlying windows
- **UFO image rendering** — UFO.png loaded as NSImage, ~120×120px, Retina-aware
- **Floating animation** — Sine-wave vertical oscillation (10–15px amplitude, ~3s period) + slight horizontal drift (3–5px), implemented via Core Animation (`CABasicAnimation`)
- **Menu bar item** — `NSStatusItem` for quit access; also supports Cmd+Q

### Target Environment

- macOS 12 (Monterey)+, Apple Silicon and Intel
- Python 3.9+, managed via `uv`

### Performance Targets

- CPU: <1% at idle
- Memory: <50MB
- Startup: <2s

## Workflow Rules

- **作業完了後は必ずGitHubにコミット＆プッシュする**（機能追加・バグ修正問わず毎回）

## Phase 3 AI Integration Notes

- Uses Anthropic Claude API for folder image analysis
- Drag-and-drop folder onto UFO → AI categorizes images (landscapes, people, screenshots, food, etc.)
- Safe 3-step workflow: propose → confirm → execute (no destructive file ops without confirmation)
- Requires Anthropic API key configuration UI
- Also handles duplicate image detection
