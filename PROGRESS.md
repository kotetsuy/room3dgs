# PROGRESS — room3dgs 実装状況

最終更新: 2026-07-04 / 対象: SPEC.md v4（6機能のシンプル版）

## 全体像
- **Phase 0（写真→.ply の実現性）は PASS 済み**（詳細 `PHASE0_RESULT.md`）。WorldMirror v1.1 が gfx1151 で 3DGS `.ply` を生成できることを実機実証。
- SPEC v4 の **Web アプリは実装・E2E検証・README すべて完了**（6要件を満たす）。**タスク#10 完了**。

## 実装済みファイル（本リポジトリ /home/araki/room3dgs）
- `config.py` — パス/MAX_SETS=3/VENV_PY/WORLDMIRROR_DIR/INFER_ENV。環境変数で上書き可。
- `recon.py` — `reconstruct(set_dir)`: venv Python で WorldMirror `infer.py --save_gs` をサブプロセス実行 → `gaussians.ply` を `scene.ply` にコピー。ログは `set_dir/recon.log`。
- `server.py` — FastAPI。`/`,`/viewer`,`/api/sets`(GET/POST/DELETE),`/api/sets/{id}/reconstruct`(threadでバックグラウンド),`/status`,`/scene.ply`,`/thumb/{name}`。`/static` を StaticFiles でマウント。多重再構成は Lock で防止。meta.json に status(none/running/done/error)。
- `requirements.txt` — fastapi, uvicorn[standard], python-multipart, pillow, pillow-heif（アプリ層のみ。3DGS本体は別venv）。
- `static/index.html` + `app.js` + `style.css` — 写真UP(2枚以上/D&D)、セット最大3カード、3D作成+3秒ポーリング、3Dを見る、削除。
- `static/viewer.html` + `viewer.js` + `splat-viewer.js` — 3DGSビューア。
  - `splat-viewer.js` = **antimatter15/splat（MIT）をローカル同梱**（CDN非依存）。編集は2点のみ: (1)URL解決を `?set=<id>` → `/api/sets/<id>/scene.ply`、(2)`carousel=false`（train presetの自動巡回でブラック化を防ぐ）。3DGSの.plyを直接パース(`processPlyBuffer`)、worker深度ソート、WebGL2描画。`save:false`維持。
  - `viewer.js` = オーバーレイ配線（`?set=`からDLリンク/タイトル）。
  - 既存plyの重心は約(0.24,0.25,0.17)で原点付近、defaultViewMatrixのカメラ距離6.55で初期表示は入る想定。
- `.gitignore` — `data/` を追記済み（要件6完了、`git check-ignore` で確認済み）。

## E2E検証（2026-07-04 完了・PASS）
`~/room3dgs-work/out/Room_Cat/images` の室内8枚で全経路を実機検証。
- `.venv` 作成 + `pip install -r requirements.txt` OK。`node --check` で splat-viewer/app/viewer.js 構文OK。`import config,recon,server` OK。
- サーバ起動 → `GET /api/sets`(空)→ 8枚UP でセット作成 → `thumb`(200 image/jpeg) → `scene.ply`未生成(404)。
- `POST /reconstruct` → **infer.py が実走**（recon.log で確認、推論12.3s）→ status=done、**約130万ガウシアン**(1,301,995)。
- `GET /scene.ply` → 200 / `application/octet-stream` / 88.5MB。PLYヘッダ `element vertex 1301995` 確認。
- 境界: 4件目=400(MAX_SETS)、1枚=400(MIN_IMAGES)、DELETE→フォルダ消去OK、viewer=200。
- ヘッドレスChrome(SwiftShader)でビューアはWebGLコンテキスト生成・ply fetch・フレーム描画(ReadPixels)まで到達を確認。**130万規模の実描画は実機Chrome(GPU)で目視するのが確実**（この環境の既知制約）。
- 補足: 今回は約30秒で完了（PROGRESS初出の182秒より速い。入力が既に518px相当＋モデルウォームのため。推論自体は12.3s）。
- 検証用セットは削除済み（`data/` は .gitignore 対象、リポジトリ状態はクリーン）。

## README.md（2026-07-04 完了）
`README.md` に 概要／構成／前提（外部venv・環境変数上書き）／起動手順／撮影のコツ／API表／E2E実測 を記載。

## 前提環境（重要・再現の鍵）
- **WorldMirror 実体**: `~/room3dgs-work/HunyuanWorld-Mirror`（`infer.py`, `ckpts/model.safetensors` 5GB DL済み）。
- **推論 venv**: `~/venvs/worldmirror`（`~/.local` の torch 2.9.1+rocm7.2.1 を `userlocal.pth` で再利用）。gsplat は**スタブ**（`site-packages/gsplat/`）で代替（推論は呼ばない）。`infer.py` は `save_rendered` デフォルトを False に編集済み。requirements の open3d は 0.19.0、onnxruntime 追加済み。
- **実行時env**: `HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151`（recon.py が付与）。
- 実測: 室内8枚で約182秒/約130万ガウシアン。

## 起動（完成後）
```bash
cd /home/araki/room3dgs
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
# Chrome で http://localhost:8000/
```

## タスク状態（TaskList）
- #1-4: Phase 0（完了）
- #5 config/req/gitignore ✅ / #6 recon.py ✅ / #7 server.py ✅ / #8 front ✅ / #9 viewer ✅ / #10 E2E+README ✅
- **SPEC v4 の6要件すべて達成。実装フェーズ完了。**
