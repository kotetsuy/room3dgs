# Phase 0 実現性検証 — 結果（判定ゲート: **PASS**）

> SPEC.md の Phase 0（フィードフォワード3DGS の gfx1151 実現性検証）の結果。
> **結論: フィードフォワード3DGS（WorldMirror）を本採用し、Phase 1 以降へ進む。**

実施日: 2026-07-04 / 実機: NucBox EVO X2 (Ryzen AI MAX+ 395, gfx1151, ROCm 7.2.1)

---

## 1. 判定ゲート結論

**PASS。** iPhone 相当の室内写真（複数枚）から、gfx1151 上で **3D Gaussian Splatting の `.ply` を生成できることを実証**した。SPEC 第一候補の「フィードフォワード3DGS（WorldMirror）」をそのまま採用する。フォールバック（OpenSplat / Depth Anything V2）に倒す必要はない。

### 実証結果（室内シーン Room_Cat, 8視点）
| 項目 | 値 |
|------|-----|
| 入力 | 室内写真 8枚（`examples/realistic/Room_Cat`） |
| 推論時間 | **181.5 秒**（モデルロード除く、8枚） |
| 出力ガウシアン数 | **1,300,891** |
| `gaussians.ply` サイズ | 88.4 MB |
| PLY 形式 | 標準3DGS: `x,y,z / nx,ny,nz / f_dc_0..2 / opacity / scale_0..2 / rot_0..3`（SH次数0） |
| 併産物 | 深度8枚・法線8枚・点群(145万点)・COLMAP(cameras/images/points3D) |
| 再構成範囲 | 約 2.76 × 2.26 × 4.31（無次元, 部屋比率として妥当） |

---

## 2. 採用モデル

- **WorldMirror v1.1**（`Tencent-Hunyuan/HunyuanWorld-Mirror`, ICML 2026, weights 2025-10-22 公開）
  - HuggingFace: `tencent/HunyuanWorld-Mirror`（**非 gated**, `model.safetensors` 5.05GB）
  - **flash-attn 不要**（← SPEC が警告する CK FMHA 2時間超コンパイルを回避できる決定的理由。v2.0 は FA 必須のため v1.1 を選択）
  - 推論: `python infer.py --input_path <images> --output_path <out> --save_gs` → `gaussians.ply`

---

## 3. 環境（再現手順の要点）

torch は既に **user-site にネイティブ導入済み**（`~/.local`, torch 2.9.1+rocm7.2.1 / HIP 7.2 / `cuda.is_available()=True`）。これを専用 venv から `.pth` で再利用する（venv を消せば元に戻る）。

```bash
# 1. 専用 venv（既存 ROCm torch を再利用）
python3.12 -m venv ~/venvs/worldmirror
echo "$HOME/.local/lib/python3.12/site-packages" > ~/venvs/worldmirror/lib/python3.12/site-packages/userlocal.pth

# 2. モデル取得 + 依存（requirements の open3d==0.18.0 は 0.19.0 に緩める / onnxruntime を追加）
cd ~/room3dgs-work/HunyuanWorld-Mirror
~/venvs/worldmirror/bin/pip install -r requirements.txt   # open3d==0.19.0 に修正のこと
~/venvs/worldmirror/bin/pip install onnxruntime            # requirements 記載漏れ（sky segmentation 用）
~/venvs/worldmirror/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('tencent/HunyuanWorld-Mirror', local_dir='ckpts')"

# 3. 推論（gfx1151 環境変数）
export HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151
~/venvs/worldmirror/bin/python infer.py --input_path examples/realistic/Room_Cat --output_path out --save_gs
```

作業ディレクトリ: `~/room3dgs-work/`（`HunyuanWorld-Mirror` 本体・`gsplat` fork・`out` 出力）。重み・大容量生成物は git リポジトリ外。

---

## 4. gsplat の扱い（重要 / 既知の課題）

### 判明した事実
gsplat（`ROCm/gsplat` = `amd_gsplat`）の **ネイティブビルドは gfx1151 で不成立**。原因は明確:

- fork が **ウェーブフロント幅64（AMD Instinct / gfx942）をハードコード**（`gsplat/hip/include/Utils.cuh` の `rocprim::warp_reduce<float, 64>`、および各 Rasterize カーネルの `rocprim_warpSum<CDIM, 64>`）。
- gfx1151（RDNA3.5）は **wave32** のため、rocprim の `check_virtual_wave_size<64, size32>` が「64 > 32」で **static_assert 失敗**。
- （その他、ビルド前提として glm サブモジュール取得と、SIGBUS 回避のための `MAX_JOBS` 抑制が必要だった。アーキ自動検出は gfx1151 で正常、"unsupported CUDA calls: 0" とHIP移植自体はクリーン。）

### なぜ Phase 0 は通ったか（gsplat 不要の根拠）
WorldMirror の**フィードフォワード推論 + `.ply` エクスポートは gsplat のラスタライズを一切呼ばない**:
`GaussianSplatRenderer.render()` は `is_inference=True`（推論の既定）のとき、`predictions["splats"]` を作った直後に **早期 return**（`rasterization.py:210-212`）し、ラスタライズ（`rasterize_batches`）は学習/評価時のみ実行される。ガウシアンの予測・voxel prune・splat 生成はすべて PyTorch/ROCm 演算で完結する。
→ gsplat は「import 可能なシンボル」としてのみ必要。**軽量スタブ**（`~/venvs/worldmirror/.../gsplat/`）で代替し、推論を成立させた。

### 影響と将来課題
- **v1（本 PoC）への影響なし**: 実プロダクトの描画はブラウザの `@react-three/drei <Splat>` が行う。サーバ側 gsplat ラスタライズは infer.py の任意プレビュー動画（`--save_rendered`）専用で、無効化済み。
- **将来課題（別タスク化推奨）**: サーバ側レンダリングや 3DGS の追加最適化/学習が必要になった場合のみ、gsplat の **wave32 移植**（`64` → `32` またはアーキ駆動の `__AMDGCN_WAVEFRONT_SIZE__` 化）が要る。数値正しさの検証も別途必要。

---

## 5. Phase 1 以降への申し送り

- 再構成器の抽象インターフェース（SPEC `reconstructor.py`）の **第一実装は WorldMirror**。`infer.py` のロジック（`WorldMirror.from_pretrained` → `model(views=...)` → `save_gs_ply`）をラップする。
- 依存の注意: `open3d==0.19.0`（0.18.0 は py3.12 に無い）、`onnxruntime`（requirements 記載漏れ）を pyproject に明記する。
- gsplat はプロダクト依存から外す（スタブ or optional 扱い）。ビルド前提にしない。
- 生成 `.ply` は下流の `HANDOFF_room3dgs_genesis.md`（Poisson メッシュ化→Genesis）の入力にそのまま使える形式であることを確認済み。
