# room3dgs — Technical Documentation

*日本語版: [TECHNICALJ.md](TECHNICALJ.md)*

For installation and usage see **[README.md](README.md)**. This document covers architecture,
external dependencies, the API, verification results, and technical notes. The primary spec is
`SPEC.md`; the reconstruction backend is proven in `PHASE0_RESULT.md`.

---

## Architecture

```
┌───────────────────────────────────────────────┐
│  Chrome (localhost:8000)                       │
│   / (index.html)  : photo upload & set mgmt    │
│   /viewer         : .ply 3D display            │
└───────────────┬───────────────────────────────┘
                │ HTTP
┌───────────────▼───────────────────────────────┐
│  FastAPI (server.py)  127.0.0.1:8000           │
│   static serving static/ + JSON/file API       │
│      └─ recon.py : photo set → WorldMirror →   │
│                    scene.ply (runs infer.py as │
│                    a subprocess via venv Python)│
└───────────────┬───────────────────────────────┘
                │ read/write
┌───────────────▼───────────────────────────────┐
│  data/  ← gitignored                            │
│   sets/<set_id>/{meta.json, input/*.jpg,        │
│                  thumb/*.jpg, scene.ply}        │
└────────────────────────────────────────────────┘
```

- The frontend is plain HTML + vanilla JS (no React/build step). To work offline, all JS
  dependencies are vendored locally and **no external CDN is referenced**.
- The 3DGS viewer is **antimatter15/splat (MIT), vendored locally** (`static/splat-viewer.js`).
  Only two edits were made:
  1. URL resolution `?set=<id>` → `/api/sets/<id>/scene.ply`
  2. `carousel=false` (prevents the train-preset auto-carousel from blacking out the view)
- Set limit is `MAX_SETS = 3` (`config.py`). Concurrent reconstruction is prevented with a
  per-`set_id` lock.

---

## Directory layout

```
room3dgs/
├── README.md             # install & usage (English)
├── TECHNICAL.md          # this document (English)
├── READMEJ.md            # install & usage (Japanese)
├── TECHNICALJ.md         # technical doc (Japanese)
├── SPEC.md               # specification (primary source)
├── PHASE0_RESULT.md      # Phase 0 proof-of-concept results
├── .gitignore            # ignores data/ (requirement 6)
├── requirements.txt      # fastapi, uvicorn, python-multipart, pillow, pillow-heif
├── server.py             # FastAPI: static serving + API
├── recon.py              # photo set → scene.ply (WorldMirror wrapper)
├── config.py             # paths, MAX_SETS, venv/infer.py locations
├── static/
│   ├── index.html        # photo upload + set mgmt (max 3) + reconstruct
│   ├── viewer.html       # .ply viewer
│   ├── app.js            # index logic (fetch API)
│   ├── viewer.js         # viewer overlay wiring (DL link/title from ?set=)
│   ├── splat-viewer.js   # 3DGS rendering (antimatter15/splat, vendored, CDN-free)
│   └── style.css
└── data/                 # ← gitignored (photo & ply storage)
    └── sets/<id>/{meta.json, input/*.jpg, thumb/*.jpg, scene.ply}
```

---

## Prerequisites & external dependencies

The reconstruction backend (WorldMirror / torch-rocm) lives **outside this repository** and must be
prepared per Phase 0.

| Item | Detail |
|------|--------|
| Model | **WorldMirror v1.1** (`tencent/HunyuanWorld-Mirror`, non-gated, `model.safetensors` 5.05GB, no flash-attn) |
| Tree | `~/room3dgs-work/HunyuanWorld-Mirror` (`infer.py`, `ckpts/model.safetensors`) |
| Inference venv | `~/venvs/worldmirror` (reuses `~/.local` torch 2.9.1+rocm7.2.1 via a `.pth`) |
| gsplat | Native build fails on gfx1151 (wave32). Inference never calls the rasterizer, so it's replaced by a **lightweight stub**. Rendering happens browser-side, so no impact. |
| Run | `infer.py --input_path <dir> --output_path <out> --save_gs` → `gaussians.ply` (standard 3DGS: `x,y,z/nx,ny,nz/f_dc_0..2/opacity/scale_0..2/rot_0..3`) |
| Runtime env | `HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151` |

`recon.py` is a thin wrapper: it takes `set_dir/input/*.jpg`, runs `infer.py` as a subprocess via the
venv Python, and copies the resulting `gaussians.ply` to `set_dir/scene.ply`. It is deliberately
confined to a single "input dir → scene.ply" function to make swapping the model easy (SPEC §8).
The run log is written to `set_dir/recon.log`.

### Environment variables

The defaults in `config.py` can be overridden via environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `ROOM3DGS_VENV_PY` | `/home/araki/venvs/worldmirror/bin/python` | Python of the WorldMirror inference venv |
| `ROOM3DGS_WORLDMIRROR_DIR` | `/home/araki/room3dgs-work/HunyuanWorld-Mirror` | Tree containing `infer.py` |
| `ROOM3DGS_DATA_DIR` | `<repo>/data` | Storage for photos & ply |
| `ROOM3DGS_MAX_SETS` | `3` | Set storage limit |

Other constants (`config.py`): `MIN_IMAGES=2`, `MAX_IMAGES=40`, `MAX_IMAGE_LONG_EDGE=1600`,
`THUMB_LONG_EDGE=320`, `MAX_UPLOAD_BYTES=500MB`.

---

## API (`server.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | `index.html` (upload & management screen) |
| GET | `/viewer?set=<id>` | `viewer.html` (3D display) |
| GET | `/api/sets` | List sets (max 3, each meta) + `max` |
| POST | `/api/sets` | Create a photo set (multipart: `name` + `files[]`). 400 if over 3 or too few images |
| DELETE | `/api/sets/{id}` | Delete a set (whole folder) |
| POST | `/api/sets/{id}/reconstruct` | Start `.ply` generation in the background. Returns `running` immediately (concurrency guarded by a lock) |
| GET | `/api/sets/{id}/status` | Reconstruction state (none/running/done/error) + message + gaussian count + `has_ply` |
| GET | `/api/sets/{id}/scene.ply` | Serve the generated `.ply` (`application/octet-stream`) |
| GET | `/api/sets/{id}/thumb/{name}` | Serve a thumbnail |

- Images are `Image.convert("RGB")` + resized to a 1600px long edge on save. HEIC via `pillow-heif`.
- `meta.json` holds `id / name / created / images / status / message / num_gaussians`.
- **Path-traversal guard**: `set_id` must be alphanumeric; the thumbnail `name` allows only
  alphanumerics plus `_` and `.`.
- Binds to `127.0.0.1` only (not publicly exposed). Total upload size is capped (500MB).

---

## Verification (E2E, 2026-07-04)

The full path was verified with 8 indoor photos from `~/room3dgs-work/out/Room_Cat/images`.

| Check | Result |
|---|---|
| venv creation + `pip install` | OK |
| JS syntax check (`node --check` splat-viewer/app/viewer) | OK |
| `import config, recon, server` | OK |
| Set creation (8-image upload) | OK |
| Thumbnail serving | 200 / image/jpeg |
| `POST /reconstruct` → `infer.py` real run | inference 12.3s, **~1.3M gaussians** (1,301,995) |
| `GET /scene.ply` | 200 / octet-stream / **88.5MB**, header `element vertex 1301995` |
| Limit (4th set) | 400 (MAX_SETS) |
| Min images (1 photo) | 400 (MIN_IMAGES) |
| Delete | whole folder removed, OK |
| Viewer page | 200 |
| Viewer WebGL | reached context creation, ply fetch, and frame draw (ReadPixels) |

- This run finished in ~30s (faster than the initial 182s; inputs were already ~518px and the model
  was warm — inference itself was 12.3s).
- Headless + software GL is slow to actually rasterize ~1.3M splats. **Visual confirmation on real
  Chrome (GPU enabled) is the reliable path.**

---

## Technical notes

- **Model kept swappable via a thin layer**: `recon.py` is confined to a single "input dir →
  scene.ply" function, making it easy to swap in WorldMirror 2.0 or another method later.
- **No gsplat needed**: no server-side rendering (rendering is browser-side). A native gsplat build
  (wave32 port) is out of scope.
- **Gaussian count vs. render cost**: ~1.3M can be heavy in the browser. If needed, add optional
  voxel/opacity decimation at save time.
- The existing ply's **centroid** is ~(0.24, 0.25, 0.17), near the origin; the `defaultViewMatrix`
  camera distance of 6.55 keeps the initial view in frame.

---

## References

- WorldMirror: <https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror> (`tencent/HunyuanWorld-Mirror`)
- 3DGS WebGL viewer examples: antimatter15/splat, mkkellogg/GaussianSplats3D, SuperSplat (all vendored locally for offline use)
- Downstream (future): `HANDOFF_room3dgs_genesis.md` (`.ply` → mesh → Genesis + Franka)
