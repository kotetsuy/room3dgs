"""room3dgs — 室内3DGS PoC の Web サーバ（FastAPI）。

Chrome から写真をアップロード → 最大3セット保存 → 1セットを選んで .ply 生成 →
ブラウザで 3DGS 表示。単機ローカル・オフライン完結（127.0.0.1）。
"""
from __future__ import annotations

import io
import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # HEIC 非対応環境でも JPEG/PNG は動く
    pass

import config
import recon

config.ensure_dirs()

app = FastAPI(title="room3dgs")

# 再構成の多重起動防止（set_id 単位）
_recon_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


# ---------- meta / set helpers ----------

def _set_dir(set_id: str) -> Path:
    # パストラバーサル防止：id は英数字のみ許可
    if not set_id.isalnum():
        raise HTTPException(400, "invalid set id")
    return config.SETS_DIR / set_id


def _meta_path(set_id: str) -> Path:
    return _set_dir(set_id) / "meta.json"


def _load_meta(set_id: str) -> dict:
    p = _meta_path(set_id)
    if not p.exists():
        raise HTTPException(404, "set not found")
    return json.loads(p.read_text())


def _save_meta(meta: dict) -> None:
    (_set_dir(meta["id"]) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def _list_meta() -> list[dict]:
    out = []
    if config.SETS_DIR.exists():
        for d in sorted(config.SETS_DIR.iterdir()):
            mp = d / "meta.json"
            if mp.exists():
                try:
                    out.append(json.loads(mp.read_text()))
                except json.JSONDecodeError:
                    continue
    out.sort(key=lambda m: m.get("created", ""))
    return out


def _ply_gaussian_count(ply: Path) -> int | None:
    """PLY ヘッダから element vertex N を読む（先頭数KBのみ）。"""
    try:
        with ply.open("rb") as f:
            head = f.read(4096)
        for line in head.split(b"\n"):
            if line.startswith(b"element vertex"):
                return int(line.split()[-1])
    except Exception:
        return None
    return None


def _lock_for(set_id: str) -> threading.Lock:
    with _locks_guard:
        return _recon_locks.setdefault(set_id, threading.Lock())


# ---------- pages ----------

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((config.STATIC_DIR / "index.html").read_text())


@app.get("/viewer", response_class=HTMLResponse)
def viewer() -> HTMLResponse:
    return HTMLResponse((config.STATIC_DIR / "viewer.html").read_text())


# ---------- sets API ----------

@app.get("/api/sets")
def list_sets() -> dict:
    sets = []
    for m in _list_meta():
        sets.append({
            "id": m["id"],
            "name": m.get("name", ""),
            "created": m.get("created"),
            "images": m.get("images", []),
            "num_images": len(m.get("images", [])),
            "status": m.get("status", "none"),
            "message": m.get("message", ""),
            "num_gaussians": m.get("num_gaussians"),
            "has_ply": (_set_dir(m["id"]) / "scene.ply").exists(),
        })
    return {"sets": sets, "max": config.MAX_SETS}


@app.post("/api/sets")
async def create_set(name: str = Form(...), files: list[UploadFile] = File(...)) -> dict:
    if len(_list_meta()) >= config.MAX_SETS:
        raise HTTPException(400, f"セットは最大 {config.MAX_SETS} 個です。不要なものを削除してください")
    if len(files) < config.MIN_IMAGES:
        raise HTTPException(400, f"写真を {config.MIN_IMAGES} 枚以上選んでください")
    if len(files) > config.MAX_IMAGES:
        raise HTTPException(400, f"写真は最大 {config.MAX_IMAGES} 枚までです")

    set_id = uuid.uuid4().hex[:8]
    sdir = _set_dir(set_id)
    (sdir / "input").mkdir(parents=True, exist_ok=True)
    (sdir / "thumb").mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    total = 0
    for i, f in enumerate(files):
        raw = await f.read()
        total += len(raw)
        if total > config.MAX_UPLOAD_BYTES:
            shutil.rmtree(sdir, ignore_errors=True)
            raise HTTPException(413, "アップロード合計サイズが上限を超えました")
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            continue  # 画像でないファイルはスキップ
        img.thumbnail((config.MAX_IMAGE_LONG_EDGE, config.MAX_IMAGE_LONG_EDGE))
        fn = f"img_{i:03d}.jpg"
        img.save(sdir / "input" / fn, quality=92)
        thumb = img.copy()
        thumb.thumbnail((config.THUMB_LONG_EDGE, config.THUMB_LONG_EDGE))
        thumb.save(sdir / "thumb" / fn, quality=85)
        names.append(fn)

    if len(names) < config.MIN_IMAGES:
        shutil.rmtree(sdir, ignore_errors=True)
        raise HTTPException(400, f"有効な画像が {config.MIN_IMAGES} 枚未満でした")

    meta = {
        "id": set_id,
        "name": name.strip() or set_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "images": names,
        "status": "none",
        "message": "",
        "num_gaussians": None,
    }
    _save_meta(meta)
    return meta


@app.delete("/api/sets/{set_id}")
def delete_set(set_id: str) -> dict:
    sdir = _set_dir(set_id)
    if not sdir.exists():
        raise HTTPException(404, "set not found")
    shutil.rmtree(sdir, ignore_errors=True)
    return {"deleted": set_id}


@app.get("/api/sets/{set_id}/thumb/{name}")
def get_thumb(set_id: str, name: str) -> FileResponse:
    if not name.replace("_", "").replace(".", "").isalnum():
        raise HTTPException(400, "invalid name")
    p = _set_dir(set_id) / "thumb" / name
    if not p.exists():
        raise HTTPException(404, "thumb not found")
    return FileResponse(p)


# ---------- reconstruction ----------

def _run_reconstruction(set_id: str) -> None:
    lock = _lock_for(set_id)
    if not lock.acquire(blocking=False):
        return  # 既に実行中
    try:
        meta = _load_meta(set_id)
        meta["status"] = "running"
        meta["message"] = "3DGS 再構成中…（数分かかります）"
        _save_meta(meta)
        try:
            scene_ply = recon.reconstruct(_set_dir(set_id))
            meta = _load_meta(set_id)
            meta["status"] = "done"
            meta["message"] = "完了"
            meta["num_gaussians"] = _ply_gaussian_count(scene_ply)
            _save_meta(meta)
        except Exception as e:  # noqa: BLE001
            meta = _load_meta(set_id)
            meta["status"] = "error"
            meta["message"] = str(e)
            _save_meta(meta)
    finally:
        lock.release()


@app.post("/api/sets/{set_id}/reconstruct")
def reconstruct_set(set_id: str) -> dict:
    meta = _load_meta(set_id)
    if meta.get("status") == "running":
        return {"id": set_id, "status": "running"}
    # 即座に running にしてからバックグラウンド実行（ポーリングで status を追う）
    meta["status"] = "running"
    meta["message"] = "開始しました"
    _save_meta(meta)
    threading.Thread(target=_run_reconstruction, args=(set_id,), daemon=True).start()
    return {"id": set_id, "status": "running"}


@app.get("/api/sets/{set_id}/status")
def get_status(set_id: str) -> dict:
    meta = _load_meta(set_id)
    return {
        "id": set_id,
        "status": meta.get("status", "none"),
        "message": meta.get("message", ""),
        "num_gaussians": meta.get("num_gaussians"),
        "has_ply": (_set_dir(set_id) / "scene.ply").exists(),
    }


@app.get("/api/sets/{set_id}/scene.ply")
def get_scene_ply(set_id: str) -> FileResponse:
    p = _set_dir(set_id) / "scene.ply"
    if not p.exists():
        raise HTTPException(404, "scene.ply not found")
    return FileResponse(p, media_type="application/octet-stream", filename=f"{set_id}.ply")


# 静的アセット（js/css）。CDN 非依存でローカル配信。
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
