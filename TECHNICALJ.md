# room3dgs — 技術ドキュメント

インストール・使い方は **[READMEJ.md](READMEJ.md)** を参照。本書はアーキテクチャ・外部依存・API・
検証結果・技術メモを扱う。仕様の一次資料は `SPEC.md`、再構成基盤の実証は `PHASE0_RESULT.md`。

---

## アーキテクチャ

```
┌───────────────────────────────────────────────┐
│  Chrome (localhost:8000)                       │
│   / (index.html)  : 写真アップロード＆セット管理 │
│   /viewer         : .ply 3D 表示               │
└───────────────┬───────────────────────────────┘
                │ HTTP
┌───────────────▼───────────────────────────────┐
│  FastAPI (server.py)  127.0.0.1:8000           │
│   静的配信 static/ + JSON/ファイル API          │
│      └─ recon.py : 写真セット → WorldMirror →   │
│                    scene.ply（venv Python で   │
│                    infer.py をサブプロセス実行） │
└───────────────┬───────────────────────────────┘
                │ 読み書き
┌───────────────▼───────────────────────────────┐
│  data/  ← .gitignore 対象                       │
│   sets/<set_id>/{meta.json, input/*.jpg,        │
│                  thumb/*.jpg, scene.ply}        │
└────────────────────────────────────────────────┘
```

- フロントは素の HTML + バニラ JS（React/ビルド不要）。オフライン動作のため依存 JS はローカル同梱、**外部 CDN を参照しない**。
- 3DGS ビューアは **antimatter15/splat（MIT）をローカル同梱**（`static/splat-viewer.js`）。編集は2点のみ:
  1. URL 解決を `?set=<id>` → `/api/sets/<id>/scene.ply`
  2. `carousel=false`（train preset の自動巡回によるブラック化を防止）
- セット上限は `MAX_SETS = 3`（`config.py`）。多重再構成は set_id 単位の Lock で防止。

---

## ディレクトリ構成

```
room3dgs/
├── READMEJ.md            # インストール・使い方
├── TECHNICALJ.md         # 本書
├── SPEC.md               # 仕様書（一次資料）
├── PHASE0_RESULT.md      # Phase 0 実証結果
├── .gitignore            # data/ を無視（要件6）
├── requirements.txt      # fastapi, uvicorn, python-multipart, pillow, pillow-heif
├── server.py             # FastAPI: 静的配信 + API
├── recon.py              # 写真セット → scene.ply（WorldMirror ラッパ）
├── config.py             # パス・MAX_SETS・venv/infer.py の場所
├── static/
│   ├── index.html        # 写真UP + セット管理(最大3) + 再構成
│   ├── viewer.html       # .ply ビューア
│   ├── app.js            # index 用ロジック（fetch API）
│   ├── viewer.js         # ビューアのオーバーレイ配線（?set= から DL/タイトル）
│   ├── splat-viewer.js   # 3DGS 描画（antimatter15/splat 同梱・CDN非依存）
│   └── style.css
└── data/                 # ← .gitignore（写真・ply の保存先）
    └── sets/<id>/{meta.json, input/*.jpg, thumb/*.jpg, scene.ply}
```

---

## 前提・外部依存

再構成本体（WorldMirror / torch-rocm）は**このリポジトリの外**にある。Phase 0 で用意済みであること。

| 項目 | 内容 |
|------|------|
| 再構成モデル | **WorldMirror v1.1**（`tencent/HunyuanWorld-Mirror`, 非gated, `model.safetensors` 5.05GB, flash-attn不要） |
| 実体 | `~/room3dgs-work/HunyuanWorld-Mirror`（`infer.py`, `ckpts/model.safetensors`） |
| 推論 venv | `~/venvs/worldmirror`（`~/.local` の torch 2.9.1+rocm7.2.1 を `.pth` で再利用） |
| gsplat | ネイティブビルドは gfx1151（wave32）で不成立。推論はラスタライズを呼ばないため**軽量スタブで代替**。描画はブラウザ側なので影響なし |
| 実行 | `infer.py --input_path <dir> --output_path <out> --save_gs` → `gaussians.ply`（標準3DGS: `x,y,z/nx,ny,nz/f_dc_0..2/opacity/scale_0..2/rot_0..3`） |
| 実行時 env | `HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151` |

`recon.py` は `set_dir/input/*.jpg` を受け取り、venv Python で `infer.py` をサブプロセス実行、
生成された `gaussians.ply` を `set_dir/scene.ply` にコピーするだけの薄いラッパ。
モデル差し替えを容易にするため「入力ディレクトリ → scene.ply」の1関数に閉じてある（SPEC §8）。
実行ログは `set_dir/recon.log`。

### 環境変数

`config.py` の既定値は環境変数で上書きできる。

| 変数 | 既定 | 用途 |
|---|---|---|
| `ROOM3DGS_VENV_PY` | `/home/araki/venvs/worldmirror/bin/python` | WorldMirror 推論 venv の Python |
| `ROOM3DGS_WORLDMIRROR_DIR` | `/home/araki/room3dgs-work/HunyuanWorld-Mirror` | `infer.py` のあるツリー |
| `ROOM3DGS_DATA_DIR` | `<repo>/data` | 写真・ply の保存先 |
| `ROOM3DGS_MAX_SETS` | `3` | セット保存上限 |

その他の定数（`config.py`）: `MIN_IMAGES=2`, `MAX_IMAGES=40`, `MAX_IMAGE_LONG_EDGE=1600`,
`THUMB_LONG_EDGE=320`, `MAX_UPLOAD_BYTES=500MB`。

---

## API 仕様（`server.py`）

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/` | `index.html`（アップロード＆管理画面） |
| GET | `/viewer?set=<id>` | `viewer.html`（3D表示） |
| GET | `/api/sets` | セット一覧（最大3、各 meta）+ `max` を返す |
| POST | `/api/sets` | 写真セット新規作成（multipart: `name` + `files[]`）。3件超は 400、枚数不足は 400 |
| DELETE | `/api/sets/{id}` | セット削除（フォルダごと） |
| POST | `/api/sets/{id}/reconstruct` | `.ply` 生成をバックグラウンド開始。即 `running` を返す（多重起動は Lock で抑止） |
| GET | `/api/sets/{id}/status` | 再構成状態（none/running/done/error）+ メッセージ + ガウシアン数 + `has_ply` |
| GET | `/api/sets/{id}/scene.ply` | 生成済み `.ply` を配信（`application/octet-stream`） |
| GET | `/api/sets/{id}/thumb/{name}` | サムネイル配信 |

- 画像は保存時に `Image.convert("RGB")` + 長辺 1600px リサイズ。HEIC は `pillow-heif` で対応。
- `meta.json` に `id / name / created / images / status / message / num_gaussians` を保持。
- **パストラバーサル対策**: `set_id` は英数字のみ許可、`thumb` の `name` も `_`/`.` 以外は英数字のみ。
- `127.0.0.1` のみ待ち受け（外部非公開）。アップロード合計サイズに上限（500MB）。

---

## 動作確認（E2E 実測 / 2026-07-04）

`~/room3dgs-work/out/Room_Cat/images` の室内 8 枚で全経路を検証済み。

| 検証項目 | 結果 |
|---|---|
| venv 作成 + `pip install` | OK |
| JS 構文チェック（`node --check` splat-viewer/app/viewer） | OK |
| `import config, recon, server` | OK |
| セット作成（8枚アップロード） | OK |
| サムネ配信 | 200 / image/jpeg |
| `POST /reconstruct` → `infer.py` 実走 | 推論 12.3s、**約130万ガウシアン**（1,301,995） |
| `GET /scene.ply` | 200 / octet-stream / **88.5MB**、ヘッダ `element vertex 1301995` |
| 上限（4件目） | 400（MAX_SETS） |
| 最小枚数（1枚） | 400（MIN_IMAGES） |
| 削除 | フォルダごと消去 OK |
| viewer ページ | 200 |
| ビューア WebGL | コンテキスト生成・ply fetch・フレーム描画（ReadPixels）まで到達を確認 |

- 今回は約 30 秒で完了（初期実測 182 秒より速い。入力が既に 518px 相当＋モデルウォームのため。推論自体は 12.3s）。
- ヘッドレス + ソフトウェア GL では 130万規模の実描画に時間がかかる。**実機 Chrome（GPU 有効）での目視が確実**。

---

## 技術メモ・注意点

- **再構成モデルは差し替え可能に薄く**: `recon.py` を「入力ディレクトリ → scene.ply」の1関数に閉じ込めてあるので、将来 WorldMirror 2.0 や他手法へ差し替えやすい。
- **gsplat 不要**: サーバ側レンダリングをしない（描画はブラウザ）。gsplat のネイティブビルド（wave32移植）はスコープ外。
- **ガウシアン数と表示の重さ**: 130万規模はブラウザで重い場合がある。必要なら保存時に voxel/opacity で間引く軽量化を後付けできる（任意）。
- **既存 ply の重心**は約 (0.24, 0.25, 0.17) で原点付近、`defaultViewMatrix` のカメラ距離 6.55 で初期表示に収まる想定。

---

## 参考

- WorldMirror: <https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror>（`tencent/HunyuanWorld-Mirror`）
- 3DGS WebGL ビューア実装例: antimatter15/splat, mkkellogg/GaussianSplats3D, SuperSplat（いずれもローカル同梱してオフライン化）
- 下流連携（将来）: `HANDOFF_room3dgs_genesis.md`（`.ply` → メッシュ化 → Genesis + Franka）
