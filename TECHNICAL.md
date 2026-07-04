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
├── requirements.txt      # app layer: fastapi, uvicorn, python-multipart, pillow, pillow-heif
├── requirements_patched.txt  # for WorldMirror (copy to the separate env; fixed upstream requirements)
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

### Building the `~/room3dgs-work` environment

The reconstruction environment lives in a work tree `~/room3dgs-work/` outside this repository (to
keep the 5GB weights and large outputs out of git). The primary source is `PHASE0_RESULT.md`;
downstream integration is `HANDOFF_room3dgs_genesis.md`.

```
~/room3dgs-work/
├── HunyuanWorld-Mirror/   # git clone (infer.py, ckpts/model.safetensors 5GB)
│   └── requirements_patched.txt   # copy of the repo's fixed requirements
├── gsplat/                # ROCm/gsplat fork (unused on gfx1151, kept for reference)
└── out/                   # inference output used for the smoke test
~/venvs/worldmirror/        # inference venv (reuses ~/.local ROCm torch via a .pth)
```

Key points (full commands in [README.md](README.md), "3. Set up the reconstruction backend"):

1. **Do not reinstall torch.** The ROCm 7.2.1 build of torch 2.9.1 is already installed natively in
   `~/.local` (user-site). Place a `userlocal.pth` in the venv (a single line pointing at
   `~/.local/lib/python3.12/site-packages`) to reuse it. Deleting the venv restores the original
   state — a non-destructive setup.
2. **Use WorldMirror v1.1.** v2.0 requires flash-attn, whose CK FMHA compile takes 2+ hours; v1.1
   avoids it and is non-gated (`tencent/HunyuanWorld-Mirror`, `model.safetensors` 5.05GB).
3. **Apply two requirements fixes** (below). The fixed list is bundled in this repo as
   `requirements_patched.txt`; copy it into `~/room3dgs-work/HunyuanWorld-Mirror/` and `pip install
   -r` it (distinct from the app-layer `requirements.txt`).

   | Upstream | Fixed | Reason |
   |---|---|---|
   | `open3d==0.18.0` | `open3d==0.19.0` | 0.18.0 has no Python 3.12 wheel |
   | (missing) | add `onnxruntime` | required by sky segmentation but omitted upstream |

4. **Download weights**: `snapshot_download('tencent/HunyuanWorld-Mirror', local_dir='ckpts')`.
5. **Drop the gsplat stub into the venv** (next section).

#### gsplat stub contents

`ROCm/gsplat` (amd_gsplat) **hardcodes wave64 (AMD Instinct / gfx942)** (e.g.
`rocprim::warp_reduce<float, 64>` in `gsplat/hip/include/Utils.cuh`), so on gfx1151 (RDNA3.5,
**wave32**) rocprim's `check_virtual_wave_size<64, 32>` fails a **static_assert** ("64 > 32") →
the native build does not succeed.

But WorldMirror's **feed-forward inference + `.ply` export never call the gsplat rasterizer**:
`GaussianSplatRenderer.render()` returns **early** right after building `predictions["splats"]` when
`is_inference=True` (the inference default) — `rasterize_batches` runs only during train/eval. So
gsplat is needed only as importable symbols, satisfied by a **lightweight stub** of three files.

`src/models/models/rasterization.py` needs exactly two imports:
`from gsplat.rendering import rasterization` and `from gsplat.strategy import DefaultStrategy`.

```
~/venvs/worldmirror/lib/python3.12/site-packages/gsplat/
├── __init__.py     # __version__ = "0.0.0-stub-gfx1151"
├── rendering.py    # def rasterization(...): raise NotImplementedError(...)
└── strategy.py     # class DefaultStrategy: pass   ← marker used in isinstance checks
```

**Impact & future work**: the app renders browser-side (`static/splat-viewer.js`), so the stub is
harmless. Only if server-side rendering (`infer.py --save_rendered`) or additional 3DGS training is
needed does a **wave32 port** of gsplat (`64` → `32`, or driving it off
`__AMDGCN_WAVEFRONT_SIZE__`) plus numerical validation become a separate task.

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
