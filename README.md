# room3dgs — Install & Usage

*日本語版: [READMEJ.md](READMEJ.md)*

A local, offline PoC demo app that generates **3D Gaussian Splatting (`.ply`)** from multiple
indoor photos and displays it in Google Chrome.

Everything is driven from `http://localhost:8000/`: upload photos → save up to 3 sets → pick one
set to generate a `.ply` → view it in 3D in the browser.

- Fully local & offline (binds to `127.0.0.1` only, no external CDN)
- Plain HTML + vanilla JS frontend (no build step)

> For architecture, API, and technical details see **[TECHNICAL.md](TECHNICAL.md)**.

---

## Requirements

- **PC**: AMD Ryzen AI MAX+ 395 (Strix Halo, gfx1151 / RDNA3.5) / 48GB unified
- **OS**: Ubuntu 24.04 LTS, **ROCm**: 7.2.1, **Python**: 3.12
- **Browser**: Google Chrome (for the upload and viewer HTML)
- No network needed (except the initial model download)

---

## Installation

### 1. Clone the repository

```bash
git clone git@github.com:kotetsuy/room3dgs.git
# or: git clone https://github.com/kotetsuy/room3dgs.git
cd room3dgs
```

### 2. Install the app-layer dependencies

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Set up the reconstruction backend (build `~/room3dgs-work`)

The core of `.ply` generation, **WorldMirror (feed-forward 3DGS)**, runs in a work tree
`~/room3dgs-work/` **outside this repository** — this keeps the 5GB weights and large outputs out of
git. The steps below follow `PHASE0_RESULT.md` / `HANDOFF_room3dgs_genesis.md`.

> **Prerequisite**: a ROCm 7.2.1 build of PyTorch is already installed **natively in the user-site**
> (`~/.local`, torch 2.9.1+rocm7.2.1, `python -c "import torch; print(torch.cuda.is_available())"`
> prints `True`). The dedicated venv only reuses this torch via a `.pth`; it never reinstalls torch.

```bash
mkdir -p ~/room3dgs-work && cd ~/room3dgs-work

# 3-1. Get the WorldMirror v1.1 tree (v1.1 needs no flash-attn)
git clone https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

# 3-2. Create the inference venv and reuse the existing ROCm torch via a .pth (no torch reinstall)
python3.12 -m venv ~/venvs/worldmirror
echo "$HOME/.local/lib/python3.12/site-packages" \
  > ~/venvs/worldmirror/lib/python3.12/site-packages/userlocal.pth

# 3-3. Install deps using the fixed requirements bundled in this repo
#      Changes vs. upstream: open3d 0.18.0→0.19.0 (py3.12) + onnxruntime added. See TECHNICAL.md.
cp ~/room3dgs/requirements_patched.txt ~/room3dgs-work/HunyuanWorld-Mirror/
cd HunyuanWorld-Mirror
~/venvs/worldmirror/bin/pip install -r requirements_patched.txt

# 3-4. Download the weights (model.safetensors 5.05GB, non-gated) into ckpts/
~/venvs/worldmirror/bin/python -c "from huggingface_hub import snapshot_download; \
  snapshot_download('tencent/HunyuanWorld-Mirror', local_dir='ckpts')"

# 3-5. One-line infer.py fix: default --save_rendered to False (required on gfx1151)
#      Left at the upstream default (True) every run tries to render a video, which calls the
#      gsplat rasterizer (the stub below) and dies with NotImplementedError. recon.py relies on
#      this default too (it doesn't pass the flag), so the fix is mandatory.
sed -i 's/"--save_rendered", action="store_true", default=True/"--save_rendered", action="store_true", default=False/' infer.py
```

**gsplat stub (required on gfx1151)**: WorldMirror imports `gsplat`, but the AMD gsplat fork
hardcodes wave64 and won't compile on gfx1151 (wave32). However, **feed-forward inference and `.ply`
export never call the gsplat rasterizer** (`render()` returns early during inference). So we drop in
a lightweight stub that only satisfies the imports (rationale in
[TECHNICAL.md](TECHNICAL.md#gsplat-stub-contents)):

```bash
GS=~/venvs/worldmirror/lib/python3.12/site-packages/gsplat
mkdir -p "$GS"
printf '__version__ = "0.0.0-stub-gfx1151"\n' > "$GS/__init__.py"
printf 'def rasterization(*a, **k):\n    raise NotImplementedError("gsplat stub on gfx1151")\n' > "$GS/rendering.py"
printf 'class DefaultStrategy:\n    pass\n' > "$GS/strategy.py"
```

**Smoke test (optional)**: the bundled 8 indoor photos exercise the full path to `.ply`.

```bash
cd ~/room3dgs-work/HunyuanWorld-Mirror
export HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151
~/venvs/worldmirror/bin/python infer.py \
  --input_path examples/realistic/Room_Cat --output_path out --save_gs
# → success if out/.../gaussians.ply (~1.3M gaussians) appears
```

This gives you the two things the app (`server.py`/`recon.py`) points at:

- **WorldMirror tree**: `~/room3dgs-work/HunyuanWorld-Mirror` (`infer.py`, `ckpts/model.safetensors`)
- **Inference venv**: `~/venvs/worldmirror`

If you keep them elsewhere, override via environment variables (see [TECHNICAL.md](TECHNICAL.md#environment-variables)).

---

## Running / Stopping

```bash
cd room3dgs
./start_all.sh   # start the server in the background (127.0.0.1:8000)
./stop_all.sh    # stop the server
```

`start_all.sh` launches `uvicorn`, writing the PID to `run/server.pid` and logs to
`run/server.log` (double-start is prevented automatically). The host/port can be
overridden via environment variables:

```bash
HOST=0.0.0.0 PORT=9000 ./start_all.sh
```

Once started, open **http://localhost:8000/** in Chrome.

<details>
<summary>Starting directly without the scripts</summary>

```bash
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```
</details>

---

## Usage

1. **Upload photos**
   Select multiple photos (drag & drop supported), give the set a name, and click Save. You can
   store **up to 3 sets**.

2. **Create the 3D model**
   Click "Create 3D from these photos" on a card. Reconstruction runs in the background; wait until
   the status goes **running → done** (a few minutes, progress is polled automatically).

3. **View in 3D**
   Once done, "View 3D" opens `/viewer?set=<id>`. Rotate/pan/zoom with the mouse. The `.ply` can
   also be downloaded.

4. **Delete unwanted sets**
   Use the delete button on a card to remove a whole set (free up a slot when all 3 are full).

---

## Shooting tips

- **8–15 photos of the same room with good overlap.** The minimum is 2, but too few tends to fail.
- Shift your viewpoint gradually so adjacent photos overlap by ~60–70%.
- Keep exposure and white balance roughly constant. Avoid strong moving subjects (e.g. walking people).
- HEIC is fine (converted via `pillow-heif`). Photos are resized to a 1600px long edge on save.

---

## Troubleshooting

- **"Maximum of 3 sets"**: delete an unneeded set before creating a new one.
- **Status becomes `error`**: `data/sets/<id>/recon.log` holds the `infer.py` output. Check the
  WorldMirror venv, weights, and the gfx1151 environment variables.
- **Viewer is slow / blank**: ~1.3M splats render reliably only on real Chrome with GPU enabled.
  See [TECHNICAL.md](TECHNICAL.md) for details.
