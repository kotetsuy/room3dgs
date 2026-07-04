"""写真セット → scene.ply（WorldMirror フィードフォワード3DGS）。

要件1 & 4。入力ディレクトリを受け取り scene.ply を返すだけの薄いラッパにして、
将来モデルを差し替えやすくする（SPEC §8）。

WorldMirror は別 venv（config.VENV_PY）・別ツリー（config.WORLDMIRROR_DIR）にあり、
`infer.py --save_gs` を gfx1151 環境変数付きでサブプロセス実行する。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import config


class ReconError(RuntimeError):
    pass


def _check_prerequisites(input_dir: Path) -> list[Path]:
    if not config.VENV_PY.exists():
        raise ReconError(f"WorldMirror の venv Python が見つかりません: {config.VENV_PY}")
    infer = config.WORLDMIRROR_DIR / "infer.py"
    if not infer.exists():
        raise ReconError(f"WorldMirror の infer.py が見つかりません: {infer}")
    images = sorted(
        p for p in input_dir.glob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if len(images) < config.MIN_IMAGES:
        raise ReconError(f"画像が {config.MIN_IMAGES} 枚未満です（{len(images)} 枚）")
    return images


def reconstruct(set_dir: Path) -> Path:
    """set_dir/input/*.jpg から set_dir/scene.ply を生成して返す。

    失敗時は ReconError を送出。実行ログは set_dir/recon.log に残す。
    """
    input_dir = set_dir / "input"
    _check_prerequisites(input_dir)

    out_dir = set_dir / "_recon_out"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, **config.INFER_ENV}
    cmd = [
        str(config.VENV_PY),
        "infer.py",
        "--input_path", str(input_dir),
        "--output_path", str(out_dir),
        "--save_gs",
    ]

    log_path = set_dir / "recon.log"
    with log_path.open("w") as log:
        log.write(f"$ {' '.join(cmd)}\n(cwd={config.WORLDMIRROR_DIR})\n\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(config.WORLDMIRROR_DIR),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if proc.returncode != 0:
        raise ReconError(f"infer.py が失敗しました（exit {proc.returncode}）。詳細は {log_path.name} を参照")

    produced = sorted(out_dir.rglob("gaussians.ply"))
    if not produced:
        raise ReconError("gaussians.ply が生成されませんでした（詳細は recon.log）")

    scene_ply = set_dir / "scene.ply"
    shutil.copy2(produced[0], scene_ply)
    shutil.rmtree(out_dir, ignore_errors=True)
    return scene_ply
