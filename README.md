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

### 3. Set up the reconstruction backend (WorldMirror)

The core of `.ply` generation, **WorldMirror (feed-forward 3DGS)**, runs in a separate environment
**outside this repository**. Follow the Phase 0 procedure (`PHASE0_RESULT.md`) to prepare:

- **WorldMirror tree**: `~/room3dgs-work/HunyuanWorld-Mirror` (`infer.py`, `ckpts/model.safetensors`, 5GB)
- **Inference venv**: `~/venvs/worldmirror` (torch 2.9.1+rocm7.2.1)

If you keep them elsewhere, override via environment variables (see [TECHNICAL.md](TECHNICAL.md#environment-variables)).

---

## Running

```bash
cd room3dgs
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000/** in Chrome.

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
