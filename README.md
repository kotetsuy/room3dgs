# room3dgs

複数枚の室内写真から **3D Gaussian Splatting（`.ply`）** を生成し、Google Chrome 上で表示する
ローカル完結・オフラインの PoC デモアプリ。

写真アップロード → 最大3セット保存 → 1セットを選んで `.ply` 生成 → ブラウザで 3D 表示、までを
`http://localhost:8000/` から操作できる。再構成の中核は Phase 0 で実証済みの
**WorldMirror v1.1（フィードフォワード3DGS）on gfx1151**（`PHASE0_RESULT.md` 参照）。

- 単機ローカル・オフライン完結（`127.0.0.1` のみ待ち受け、外部 CDN 非参照）
- フロントは素の HTML + バニラ JS（ビルド不要）
- 3DGS ビューアは antimatter15/splat（MIT）をローカル同梱

---

## 構成

```
room3dgs/
├── server.py            # FastAPI: 静的配信 + JSON/ファイル API
├── recon.py             # 写真セット → scene.ply（WorldMirror ラッパ）
├── config.py            # パス・MAX_SETS・venv/infer.py の場所（環境変数で上書き可）
├── requirements.txt     # アプリ層の依存（3DGS 本体は別 venv）
├── static/              # index / viewer の HTML・JS・CSS
└── data/                # ← .gitignore（写真・ply の保存先）
    └── sets/<id>/{meta.json, input/*.jpg, thumb/*.jpg, scene.ply}
```

詳細な仕様は `SPEC.md`、再構成基盤の実証結果は `PHASE0_RESULT.md`。

---

## 前提

再構成本体（WorldMirror / torch-rocm）は**このリポジトリの外**にある。Phase 0 の手順で以下を用意済みであること:

- **WorldMirror 実体**: `~/room3dgs-work/HunyuanWorld-Mirror`（`infer.py`, `ckpts/model.safetensors` 5GB）
- **推論 venv**: `~/venvs/worldmirror`（torch 2.9.1+rocm7.2.1）

場所を変えている場合は環境変数で上書きできる（`config.py`）:

| 変数 | 既定 |
|---|---|
| `ROOM3DGS_VENV_PY` | `/home/araki/venvs/worldmirror/bin/python` |
| `ROOM3DGS_WORLDMIRROR_DIR` | `/home/araki/room3dgs-work/HunyuanWorld-Mirror` |
| `ROOM3DGS_DATA_DIR` | `<repo>/data` |
| `ROOM3DGS_MAX_SETS` | `3` |

---

## 起動

```bash
cd /home/araki/room3dgs
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

Chrome で **http://localhost:8000/** を開く。

1. 写真を複数枚選び（ドラッグ&ドロップ可）、名前を付けて保存（**最大3セット**）
2. カードの「この写真で3Dを作成」→ 状態が **done** になるまで待つ（数分／進捗はポーリング表示）
3. 「3Dを見る」で `/viewer?set=<id>` が開く。マウスで回転・パン・ズーム、`.ply` はダウンロード可

---

## 撮影のコツ

- **同一室内を重なりを持たせて 8〜15 枚**。最低 2 枚だが、少なすぎると破綻しやすい。
- 隣り合う写真が 6〜7 割ほど重なるよう、少しずつ視点をずらして撮る。
- 露出・ホワイトバランスはなるべく一定に。強い動体（歩く人など）は避ける。
- HEIC も可（`pillow-heif` で変換）。保存時に長辺 1600px へリサイズされる。

---

## API

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/` | アップロード＆セット管理画面 |
| GET | `/viewer?set=<id>` | 3DGS ビューア |
| GET | `/api/sets` | セット一覧（最大3）+ 上限 |
| POST | `/api/sets` | 写真セット新規作成（multipart: `name` + `files[]`）。3件超は 400 |
| DELETE | `/api/sets/{id}` | セット削除（フォルダごと） |
| POST | `/api/sets/{id}/reconstruct` | `.ply` 生成をバックグラウンド開始（即 running を返す） |
| GET | `/api/sets/{id}/status` | 再構成状態（none/running/done/error）+ ガウシアン数 |
| GET | `/api/sets/{id}/scene.ply` | 生成済み `.ply` を配信 |
| GET | `/api/sets/{id}/thumb/{name}` | サムネイル配信 |

---

## 動作確認（E2E 実測 / 2026-07-04）

`~/room3dgs-work/out/Room_Cat/images` の室内 8 枚で全経路を検証済み:

- アップロード → セット作成 → サムネ配信（200）
- `POST /reconstruct` → `infer.py` が実走（推論 12.3s）→ **約130万ガウシアン**の `scene.ply`（88.5MB）を生成
- `GET /scene.ply` で配信（200, `application/octet-stream`）
- セット上限（4件目 400）・最小枚数（1枚 400）・削除・ビューアの WebGL 描画開始を確認

> ビューアは 130万規模のスプラットをブラウザ側で描画するため、実機 Chrome（GPU 有効）での目視が確実。
> ヘッドレス + ソフトウェア GL では描画に時間がかかる。
