# room3dgs — インストール & 使い方

*English: [README.md](README.md)*

複数枚の室内写真から **3D Gaussian Splatting（`.ply`）** を生成し、Google Chrome 上で表示する
ローカル完結・オフラインの PoC デモアプリ。

写真アップロード → 最大3セット保存 → 1セットを選んで `.ply` 生成 → ブラウザで 3D 表示、までを
`http://localhost:8000/` から操作できる。

- 単機ローカル・オフライン完結（`127.0.0.1` のみ待ち受け、外部 CDN 非参照）
- フロントは素の HTML + バニラ JS（ビルド不要）

> アーキテクチャ・API・技術詳細は **[TECHNICALJ.md](TECHNICALJ.md)** を参照。

---

## 動作環境

- **PC**: AMD Ryzen AI MAX+ 395（Strix Halo, gfx1151 / RDNA3.5）/ 48GB unified
- **OS**: Ubuntu 24.04 LTS、**ROCm**: 7.2.1、**Python**: 3.12
- **ブラウザ**: Google Chrome（アップロード用・ビューア用の HTML を表示）
- ネットワーク不要（初回のモデル取得時のみ要）

---

## インストール

### 1. リポジトリを取得

```bash
git clone git@github.com:kotetsuy/room3dgs.git
# または: git clone https://github.com/kotetsuy/room3dgs.git
cd room3dgs
```

### 2. アプリ層の依存をインストール

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. 再構成本体（WorldMirror）を用意（`~/room3dgs-work` の構築）

`.ply` 生成の中核 **WorldMirror（フィードフォワード3DGS）** は、このリポジトリの外の作業ツリー
`~/room3dgs-work/` で動く。重み（5GB）や大容量の生成物を git 管理外に置くための分離。
以下は `PHASE0_RESULT.md` / `HANDOFF_room3dgs_genesis.md` に沿った実際の構築手順。

> **前提**: ROCm 7.2.1 対応の PyTorch が **user-site にネイティブ導入済み**であること
> （`~/.local`, torch 2.9.1+rocm7.2.1, `python -c "import torch; print(torch.cuda.is_available())"` が `True`）。
> 専用 venv はこの torch を `.pth` で再利用するだけで、torch 自体は入れ直さない。

```bash
mkdir -p ~/room3dgs-work && cd ~/room3dgs-work

# 3-1. WorldMirror v1.1 本体を取得（flash-attn 不要の v1.1 を使う）
git clone https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

# 3-2. 推論用 venv を作り、既存の ROCm torch を .pth で再利用（torch は入れ直さない）
python3.12 -m venv ~/venvs/worldmirror
echo "$HOME/.local/lib/python3.12/site-packages" \
  > ~/venvs/worldmirror/lib/python3.12/site-packages/userlocal.pth

# 3-3. 依存をインストール（本リポジトリ同梱の修正版 requirements を使う）
#      上流からの変更: open3d 0.18.0→0.19.0（py3.12 対応）+ onnxruntime 追加。詳細は TECHNICALJ。
cp ~/room3dgs/requirements_patched.txt ~/room3dgs-work/HunyuanWorld-Mirror/
cd HunyuanWorld-Mirror
~/venvs/worldmirror/bin/pip install -r requirements_patched.txt

# 3-4. 重み（model.safetensors 5.05GB, 非gated）を ckpts/ に取得
~/venvs/worldmirror/bin/python -c "from huggingface_hub import snapshot_download; \
  snapshot_download('tencent/HunyuanWorld-Mirror', local_dir='ckpts')"
```

**gsplat スタブ（gfx1151 では必須）**: WorldMirror は `gsplat` を import するが、AMD の gsplat fork は
wave64 ハードコードのため gfx1151（wave32）でビルドできない。ただし**フィードフォワード推論と `.ply`
エクスポートは gsplat のラスタライズを一切呼ばない**（`render()` が推論時に早期 return）。そこで import
だけ満たす軽量スタブを venv に置く（詳細と根拠は [TECHNICALJ.md](TECHNICALJ.md#gsplat-スタブの中身)）:

```bash
GS=~/venvs/worldmirror/lib/python3.12/site-packages/gsplat
mkdir -p "$GS"
printf '__version__ = "0.0.0-stub-gfx1151"\n' > "$GS/__init__.py"
printf 'def rasterization(*a, **k):\n    raise NotImplementedError("gsplat stub on gfx1151")\n' > "$GS/rendering.py"
printf 'class DefaultStrategy:\n    pass\n' > "$GS/strategy.py"
```

**動作確認（任意）**: 付属の室内 8 枚で `.ply` 生成まで通ることを確認できる。

```bash
cd ~/room3dgs-work/HunyuanWorld-Mirror
export HSA_OVERRIDE_GFX_VERSION=11.5.1 HSA_USE_SVM=0 HSA_ENABLE_SDMA=0 PYTORCH_ROCM_ARCH=gfx1151
~/venvs/worldmirror/bin/python infer.py \
  --input_path examples/realistic/Room_Cat --output_path out --save_gs
# → out/.../gaussians.ply（約130万ガウシアン）が出れば成功
```

これで本アプリ（`server.py`/`recon.py`）が参照する 2 つが揃う:

- **WorldMirror 実体**: `~/room3dgs-work/HunyuanWorld-Mirror`（`infer.py`, `ckpts/model.safetensors`）
- **推論 venv**: `~/venvs/worldmirror`

場所を変えている場合は環境変数で上書きできる（詳細は [TECHNICALJ.md](TECHNICALJ.md#環境変数)）。

---

## 起動

```bash
cd room3dgs
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

Chrome で **http://localhost:8000/** を開く。

---

## 使い方

1. **写真をアップロード**
   写真を複数枚選び（ドラッグ&ドロップ可）、セット名を付けて「保存」。セットは**最大3つ**まで保存できる。

2. **3D を作成**
   カードの「この写真で3Dを作成」を押す。再構成はバックグラウンドで走り、状態が
   **running → done** に変わるまで待つ（数分、進捗は自動ポーリング表示）。

3. **3D を見る**
   done になったら「3Dを見る」で `/viewer?set=<id>` が開く。
   マウスで回転・パン・ズーム。`.ply` はダウンロードもできる。

4. **不要なセットを削除**
   カードの削除ボタンでセットごと消せる（3つ埋まったら削除して枠を空ける）。

---

## 撮影のコツ

- **同一室内を重なりを持たせて 8〜15 枚**。最低 2 枚だが、少なすぎると破綻しやすい。
- 隣り合う写真が 6〜7 割ほど重なるよう、少しずつ視点をずらして撮る。
- 露出・ホワイトバランスはなるべく一定に。強い動体（歩く人など）は避ける。
- HEIC も可（`pillow-heif` で変換）。保存時に長辺 1600px へリサイズされる。

---

## トラブルシューティング

- **「セットは最大 3 個です」**: 不要なセットを削除してから新規作成する。
- **状態が `error` になる**: `data/sets/<id>/recon.log` に `infer.py` の出力が残る。WorldMirror の venv・重み・環境変数（gfx1151）を確認。
- **ビューアが重い / 表示されない**: 130万規模のスプラットは GPU 有効な実機 Chrome での表示が確実。詳細は [TECHNICALJ.md](TECHNICALJ.md) を参照。
