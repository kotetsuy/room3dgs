# room3dgs — インストール & 使い方

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

### 3. 再構成本体（WorldMirror）を用意

`.ply` 生成の中核 **WorldMirror（フィードフォワード3DGS）** は、このリポジトリの外にある別環境で動く。
Phase 0（`PHASE0_RESULT.md`）の手順で以下を用意しておくこと:

- **WorldMirror 実体**: `~/room3dgs-work/HunyuanWorld-Mirror`（`infer.py`, `ckpts/model.safetensors` 5GB）
- **推論 venv**: `~/venvs/worldmirror`（torch 2.9.1+rocm7.2.1）

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
