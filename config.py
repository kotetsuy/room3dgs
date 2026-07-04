"""アプリ設定（パス・上限・WorldMirror 実行環境）。

環境変数で上書き可能。既定値は Phase 0（PHASE0_RESULT.md）で構築した実機構成に一致。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 保存先（要件6: data/ は .gitignore 対象）
DATA_DIR = Path(os.environ.get("ROOM3DGS_DATA_DIR", BASE_DIR / "data"))
SETS_DIR = DATA_DIR / "sets"
STATIC_DIR = BASE_DIR / "static"

# セット上限（要件3）
MAX_SETS = int(os.environ.get("ROOM3DGS_MAX_SETS", "3"))

# アップロード制約
MIN_IMAGES = 2
MAX_IMAGES = 40
MAX_IMAGE_LONG_EDGE = 1600           # 保存時の長辺リサイズ
THUMB_LONG_EDGE = 320
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 1リクエストの合計上限

# WorldMirror（Phase 0 で用意した実体。本リポジトリ外）
VENV_PY = Path(os.environ.get("ROOM3DGS_VENV_PY", "/home/araki/venvs/worldmirror/bin/python"))
WORLDMIRROR_DIR = Path(os.environ.get("ROOM3DGS_WORLDMIRROR_DIR", "/home/araki/room3dgs-work/HunyuanWorld-Mirror"))

# gfx1151 実行時環境変数（recon の infer.py 実行に付与）
INFER_ENV = {
    "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
    "HSA_USE_SVM": "0",
    "HSA_ENABLE_SDMA": "0",
    "PYTORCH_ROCM_ARCH": "gfx1151",
}


def ensure_dirs() -> None:
    SETS_DIR.mkdir(parents=True, exist_ok=True)
