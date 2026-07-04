# 室内3DGS PoC デモアプリ 仕様書（2026-07 改訂・シンプル版）

> **更新履歴 / Changelog**
> - **2026-07 v4【GOAL簡素化】**: ゴールを6機能に絞る。「複数枚の写真から3D `.ply` を作る／Chrome から写真をアップロードする HTML／写真セットを最大3つ保存／1セットを選んで `.ply` を生成／`.ply` を Chrome で見る HTML／写真・plyの保存フォルダは `.gitignore`」。iPhoneプラグイン・React/Vite・プリセットのライブ再構成分岐など旧仕様の複雑要素は撤去。技術基盤は Phase 0 で実証済みの WorldMirror（フィードフォワード3DGS）on gfx1151 を継続採用。
> - **2026-06 v3〜v1**: （旧仕様。フィードフォワード3DGS 第一候補化、単機ローカル、SAM系検討など。→ v4 で簡素化）

---

## 0. ゴール（この6つがすべて）

1. **複数枚の写真から 3D `.ply`（3D Gaussian Splatting）を作成する**
2. **写真を登録するための HTML を作り、Google Chrome からアップロードできる**
3. **写真は複数セット（最大3つ）を保存できる**
4. **1つのセットを選んで 3D `.ply` ファイルを作成する**
5. **3D `.ply` ファイルを Google Chrome で表示できる HTML を作成する**
6. **写真の保存フォルダと 3D `.ply` の保存フォルダは `.gitignore` する**

外部ネットワーク・クラウド不要、単機ローカル・オフライン完結。すべて Linux PC 上の Chrome から `http://localhost:8000/` で操作する。

---

## 1. 前提（Phase 0 実証済み・`PHASE0_RESULT.md` 参照）

写真 →（フィードフォワード3DGS）→ `.ply` の中核は gfx1151 実機で**実証済み**。本アプリはこれを Web からアクセスできるようラップするだけ。

| 項目 | 内容 |
|------|------|
| 再構成モデル | **WorldMirror v1.1**（`tencent/HunyuanWorld-Mirror`, 非gated, `model.safetensors` 5.05GB, flash-attn不要） |
| 実行 | `infer.py --input_path <images_dir> --output_path <out> --save_gs` → `gaussians.ply`（標準3DGS: `x,y,z/nx,ny,nz/f_dc_0..2/opacity/scale_0..2/rot_0..3`） |
| 実績 | 室内8枚で 約182秒 / 約130万ガウシアン |
| Python環境 | venv `~/venvs/worldmirror`（`~/.local` の torch 2.9.1+rocm7.2.1 を `.pth` で再利用） |
| gsplat | ネイティブビルドは gfx1151（wave32）で不成立。推論はラスタライズを呼ばないため**軽量スタブで代替**。プロダクト描画はブラウザ側で行うので影響なし |
| 実行時env | `HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151` |

> WorldMirror 本体・重み・作業物は `~/room3dgs-work/` 側に置く（本リポジトリ外）。本アプリからは venv の Python で `infer.py` を呼び出す。

---

## 2. 実行環境

- **PC**: GMKtec NucBox EVO X2 / AMD Ryzen AI MAX+ 395 (Strix Halo, gfx1151 / RDNA3.5) / 48GB unified
- **OS**: Ubuntu 24.04 LTS、**ROCm**: 7.2.1、**Python**: 3.12
- **ブラウザ**: Google Chrome（アップロード用・ビューア用の HTML を表示）
- ネットワーク不要（初回のモデル取得時のみ要）

---

## 3. アーキテクチャ（最小構成）

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
│   sets/<set_id>/                               │
│     ├── meta.json      # 名前・作成日時・画像一覧 │
│     │                  #  ・状態(none/running/  │
│     │                  #  done/error)          │
│     ├── input/*.jpg    # アップロードされた写真   │
│     └── scene.ply      # 生成された 3DGS スプラット│
└────────────────────────────────────────────────┘
```

- **フロントは素の HTML + バニラ JS**（React/ビルド不要）。オフライン動作のため、依存 JS はローカルに同梱し外部 CDN を参照しない。
- セット上限は `MAX_SETS = 3`（`server.py` の定数）。

---

## 4. ディレクトリ構成

```
room3dgs/
├── SPEC.md                 # 本書
├── README.md               # 起動手順・撮影のコツ
├── PHASE0_RESULT.md        # Phase 0 実証結果（既存）
├── .gitignore              # data/ を無視（要件6）
├── requirements.txt        # fastapi, uvicorn, python-multipart, pillow, pillow-heif
├── server.py               # FastAPI: 静的配信 + API
├── recon.py                # 写真セット → scene.ply（WorldMirror ラッパ）
├── config.py               # パス・MAX_SETS・venv/infer.py の場所
├── static/
│   ├── index.html          # 要件2,3,4: 写真UP + セット管理(最大3) + 再構成
│   ├── viewer.html         # 要件5: .ply ビューア
│   ├── app.js              # index 用ロジック（fetch API）
│   ├── viewer.js           # .ply 読込 + WebGL スプラット描画
│   ├── splat-viewer.js     # 3DGS 描画ライブラリ（ローカル同梱・CDN非依存）
│   └── style.css
└── data/                   # ← .gitignore（写真・ply の保存先）
    └── sets/<set_id>/{meta.json, input/*.jpg, scene.ply}
```

---

## 5. API 仕様（`server.py`）

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/` | `index.html`（アップロード＆管理画面） |
| GET | `/viewer?set=<id>` | `viewer.html`（3D表示） |
| GET | `/api/sets` | セット一覧（最大3、各 meta.json）を返す |
| POST | `/api/sets` | 写真セットを新規作成（multipart で複数画像 + 名前）。3件超なら 400 |
| DELETE | `/api/sets/{id}` | セット削除（フォルダごと） |
| POST | `/api/sets/{id}/reconstruct` | そのセットの写真で `.ply` を生成（バックグラウンド実行、状態を meta.json に記録） |
| GET | `/api/sets/{id}/status` | 再構成状態（none/running/done/error）と進捗メッセージ |
| GET | `/api/sets/{id}/scene.ply` | 生成済み `.ply` を配信（ビューア/ダウンロード用） |

- 画像は保存時に `Image.convert("RGB")` + 長辺リサイズ（例 1600px）。HEIC は `pillow-heif` で対応。
- 最低2枚、推奨は同一室内を重なりを持たせて8〜15枚。

---

## 6. 各要件の実装方針

### 要件1 & 4: 写真 → `.ply` 生成（`recon.py`）
- 入力: `data/sets/<id>/input/*.jpg`、出力: `data/sets/<id>/scene.ply`
- 実装: venv Python で WorldMirror の `infer.py` をサブプロセス実行し、生成された `gaussians.ply` を `scene.ply` にコピー。
  ```python
  # 概略
  env = {**os.environ, "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
         "HSA_USE_SVM": "0", "HSA_ENABLE_SDMA": "0", "PYTORCH_ROCM_ARCH": "gfx1151"}
  subprocess.run([VENV_PY, "infer.py", "--input_path", input_dir,
                  "--output_path", out_dir, "--save_gs"], cwd=WORLDMIRROR_DIR, env=env)
  # out_dir/<name>/gaussians.ply → data/sets/<id>/scene.ply
  ```
- 再構成は時間がかかる（8枚で約3分）ので `POST /reconstruct` は即座に返し、`status` をポーリングさせる。

### 要件2 & 3: アップロード HTML（`static/index.html` + `app.js`）
- `<input type="file" accept="image/*" multiple>` で複数写真を選択（ドラッグ&ドロップ対応）。
- セット名を付けて「保存」→ `POST /api/sets`。
- 画面上部に**保存済みセット（最大3）をカード表示**（サムネ・名前・写真枚数・状態）。3件埋まっていたら新規作成を抑止し削除を促す。
- 各カードに「この写真で3Dを作成」（→ `POST /reconstruct`＋状態表示）と「3Dを見る」（→ `/viewer?set=<id>`）ボタン。

### 要件5: ビューア HTML（`static/viewer.html` + `viewer.js`）
- `GET /api/sets/{id}/scene.ply` を読み、**WebGL の 3DGS スプラットレンダラ**で表示。
- マウスで回転・パン・ズーム（OrbitControls 相当）。「.ply ダウンロード」ボタン。
- 3DGS の `.ply`（`f_dc`/`opacity`/`scale`/`rot`）を解釈できるスプラットビューアをローカル同梱（例: WebGL Gaussian Splat 実装を単一 JS にバンドル。**外部 CDN を参照しない**）。標準メッシュ用ローダでは 3DGS を正しく表示できない点に注意。

### 要件6: `.gitignore`
- `data/`（写真・`.ply` の保存先）をまるごと無視する。`.gitignore` に以下を追記:
  ```
  # room3dgs: 写真・生成plyの保存先（機微データ・大容量）
  data/
  ```

---

## 7. 動作確認手順

```bash
# 1. 依存（アプリ側）
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt   # fastapi uvicorn python-multipart pillow pillow-heif

# 2. 前提: WorldMirror 環境（PHASE0_RESULT.md の手順で ~/venvs/worldmirror と ~/room3dgs-work/HunyuanWorld-Mirror を用意済み）

# 3. 起動
uvicorn server:app --host 127.0.0.1 --port 8000

# 4. Chrome で http://localhost:8000/
#    (a) 写真を複数選んで名前を付け保存（最大3セット）
#    (b) セットを選び「3Dを作成」→ 状態が done になったら
#    (c) 「3Dを見る」で /viewer が開き、部屋を回して確認 / .ply をダウンロード
```

**完了判定（＝ゴール達成）**
- [ ] 複数写真から `.ply` が生成される（要件1）
- [ ] Chrome の HTML から写真をアップロードできる（要件2）
- [ ] 写真セットを最大3つ保存できる（要件3）
- [ ] 1セットを選んで `.ply` を作成できる（要件4）
- [ ] `.ply` を Chrome の HTML で表示できる（要件5）
- [ ] `data/`（写真・ply）が `.gitignore` されている（要件6）

---

## 8. 技術メモ・注意点

- **再構成モデルは差し替え可能に薄く**: `recon.py` を「入力ディレクトリ → scene.ply」の1関数に閉じ込めておけば、将来 WorldMirror 2.0 や他手法へ差し替えやすい。
- **gsplat 不要**: 本アプリはサーバ側レンダリングをしない（描画はブラウザ）。gsplat のネイティブビルド（wave32移植）は本ゴールのスコープ外。
- **ガウシアン数と表示の重さ**: 130万規模はブラウザで重い場合がある。必要なら保存時に voxel/opacity で間引く軽量化を後付けする（任意）。
- **セキュリティ**: `127.0.0.1` のみ待ち受け（外部非公開）。アップロード合計サイズに上限を設ける。
- **撮影のコツ（README にも記載）**: 同一室内を重なりを持たせて8〜15枚。極端に少ない枚数は破綻しやすい。

---

## 9. 参考

- WorldMirror: <https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror>（`tencent/HunyuanWorld-Mirror`）
- 3DGS WebGL ビューア実装例: antimatter15/splat, mkkellogg/GaussianSplats3D, SuperSplat（いずれもローカル同梱してオフライン化）
- 下流連携（将来）: `HANDOFF_room3dgs_genesis.md`（`.ply` → メッシュ化 → Genesis + Franka）
