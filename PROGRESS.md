# PROGRESS — room3dgs 実装状況

最終更新: 2026-07-05 / 対象: SPEC.md v4（6機能のシンプル版）
**ステータス: 本プロジェクトは 2026-07-05 に終結（下記「プロジェクト終結」参照）。**

## 全体像
- **Phase 0（写真→.ply の実現性）は PASS 済み**（詳細 `PHASE0_RESULT.md`）。WorldMirror v1.1 が gfx1151 で 3DGS `.ply` を生成できることを実機実証。
- SPEC v4 の **Web アプリは実装・E2E検証・README すべて完了**（6要件を満たす）。**タスク#10 完了**。
- その後、実写での試用と GPU ハング対策を行ったが、**出力品質が実用水準に届かず 2026-07-05 に終結**。

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

---

## 2026-07-05 セッション（運用対策・実写試用・終結）

### 運用対策1: 起動/停止スクリプト
- `start_all.sh` / `stop_all.sh` を追加。`uvicorn` を PID(`run/server.pid`)/ログ(`run/server.log`)付きでバックグラウンド起動・停止する。二重起動防止あり。

### 運用対策2: GPUハングによるログアウト問題への対処
- **現象**: 推論(`infer.py`)中に突然デスクトップからログアウトする。
- **原因**: gfx1151 は表示と計算が同一 iGPU。推論の ROCm/KFD コンピュートキューがハング（`ring comp_* timeout`、ページフォールトではない）→ KFD が回収できず MODE2 フル GPU リセット → `VRAM is lost` → gnome-shell の GL コンテキスト消滅 → GDM がセッション再起動＝ログアウト。再起動でも OOM でもない。詳細は `TECHNICAL.md` / `TECHNICALJ.md` の「既知の問題」。
- **切り分け**: `journalctl -k` で `ring comp_* timeout` / `GPU reset` / `VRAM is lost`。`page not present` が無ければハング系。
- **回避（任意・実装済み）**: GUI ターミナルから `STOP_GDM=1 ./start_all.sh`。サーバを systemd 一時ユニット `room3dgs-headless` へ切り離してから gdm を停止し、巻き添えログアウトを防ぐ。GPU リセット自体は起きるので実行中ジョブは落ちる。
- **注**: 当初あったテキストコンソール(TTY)からの HEADLESS/tmux 起動機能は、「まず GUI 上で GPU エラーを観測する」方針にしたためユーザー指示で削除（`STOP_GDM=1` の systemd 経路のみ残存）。
- **devcoredump 自動退避**: amdgpu の GPU クラッシュダンプはカーネルが既定300秒で破棄する。`/etc/udev/rules.d/99-devcoredump-capture.rules` + `/usr/local/sbin/save-devcoredump.sh` を導入し、次回ハング時に `/var/log/devcoredump/` へダンプ・dmesg を自動退避（このリポジトリ外・システム側の仕込み）。

### 実写トライアル（2026-07-05）
実際の写真でアプリを一巡し、生成〜ビューア表示まで問題なく動作することを確認。ただし**出力品質はいずれも実用水準に届かず（「イマイチ」）**。この試用ではログアウト系 GPU ハングは再発しなかった。
- **「渋谷駅」** — 8枚（風景・シーン）→ 約166万ガウシアン、推論114秒、`scene.ply` 112MB。
- **「ヘッドホン」** — 10枚（物体を中心に周囲から撮影＝360度インワード撮影）→ 約156万ガウシアン。物体の 3D 化を狙ったが品質不足。

### 品質が頭打ちになった理由（技術的限界）
- WorldMirror は**推論解像度 518px のフィードフォワード型**で、写真に合わせた最適化（学習）を行わないため、細部のシャープさ・整合性に構造的な上限がある。枚数を増やしても改善は一定で頭打ち。
- 品質を上げる本命は「WorldMirror 出力を初期値にした古典的 3DGS 最適化学習」だが、**gfx1151 では gsplat がネイティブビルド不成立**（wave64 ハードコードが wave32 で static_assert 失敗、`PHASE0_RESULT.md` / `TECHNICALJ.md` 参照）のため、ローカルでの最適化パスが塞がっている。
- 物体単体の抽出には背景ガウシアンのクロップ後処理も別途必要（未実装）。

## プロジェクト終結（2026-07-05）
- **判断**: 出力品質が実用水準に届かず、かつローカル（gfx1151）で品質を底上げする最適化学習の経路が gsplat ビルド不可で塞がっているため、**本プロジェクトはここで終結**とする。
- **残る成果物**: 動作する Web アプリ一式（写真アップロード→WorldMirror 推論→`.ply` 生成→ブラウザ 3DGS ビューア）、環境構築ドキュメント（README/TECHNICAL 日英）、GPU ハングの原因分析と回避策、devcoredump 自動退避の仕組み。
- **将来もし再開するなら**: AMD で動く 3DGS トレーナ（WebGPU ベースの Brush、ROCm ビルドのある OpenSplat 等）での最適化学習を検証する、が次の一歩。gsplat の wave32 移植はサーバ側レンダリング/学習が必要になった場合の課題として残置。
