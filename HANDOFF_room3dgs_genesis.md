# HANDOFF: room3DGS → Genesis World 統合（Franka アーム配置）

> **目的**: 既存の room3dgs-demo（feed-forward 3DGS on gfx1151）の出力を**物理シミュレーション可能なメッシュ環境**に変換し、Genesis World 上で Franka アームを動作させる。
> 最終的に「実空間 → 3DGS → 物理ツイン → ロボット動作」の OSS パイプライン全体が AMD ハードウェア上で完結することを示す。

---

## 0. プロジェクト概要

| 項目 | 内容 |
|------|------|
| **前提プロジェクト** | `room3dgs-demo`（feed-forward 3DGS via WorldMirror 2.0） |
| **後続プロジェクト** | Genesis World HANDOFF（前回作成済み） |
| **対象環境** | NucBox EVO X2 (Ryzen AI MAX+ 395, gfx1151, 96GB unified) |
| **最終ゴール** | iPhone でキャプチャした実部屋の中で Franka アームが動作する |
| **派生成果物** | Qiita 記事（仮タイトル: `iPhoneで撮った部屋でロボットアームを動かす - 3DGSからデジタルツインまでのOSSパイプライン`） |

### gfx1151 用環境変数（既存運用準拠）
```bash
export HSA_OVERRIDE_GFX_VERSION=11.5.1
export HSA_USE_SVM=0
export HSA_ENABLE_SDMA=0
```

---

## 1. アーキテクチャ概要

```
[iPhone capture]
      ↓
[room3dgs-demo / WorldMirror 2.0]
      ↓ output: gaussian.ply (3D Gaussian Splatting形式)
─────────────────────────────────────────────
[Phase 1: メッシュ抽出]
  Open3D Poisson Surface Reconstruction (CPU, ROCm非依存)
      ↓ room_mesh.obj
─────────────────────────────────────────────
[Phase 2: メッシュ後処理]
  Mesh cleaning (decimation / hole filling)
      ↓ room_clean.obj
─────────────────────────────────────────────
[Phase 3: コリジョン分解]
  V-HACD or CoACD (CPU, ROCm非依存)
      ↓ room_collision_<n>.obj × 複数
─────────────────────────────────────────────
[Phase 4: Genesis World ロード + Franka 配置]
  Genesis World → scene.add_entity(Mesh(...))
      ↓
[物理シミュレーション動作]
─────────────────────────────────────────────
[Phase 5 (optional): 高品質化]
  SuGaR / 2DGS への移行（ROCm 移植は別タスク）
```

---

## 2. 重要な背景情報

### 2.1 なぜ 3DGS を直接 Genesis に読ませられないか
Genesis World が読めるのは `URDF / MJCF / OBJ / GLB / PLY / STL`。3DGS の `.ply` は形式上は PLY だが、頂点に **3Dガウシアンの分散・回転・球面調和関数係数**を持っており、これは Genesis のメッシュパーサが想定する PLY ではない。よって**メッシュ化が必須**。

### 2.2 メッシュ化手法の選定理由
| 手法 | 品質 | gfx1151 適合性 | 採用判断 |
|------|------|---------------|----------|
| **Open3D Poisson Reconstruction** | 中 | ◎（CPU、ROCm非依存） | **Phase 1 で採用** |
| SuGaR | 高 | △（CUDA前提、移植要） | Phase 5 で挑戦 |
| 2DGS | 最高 | △（CUDA前提、移植要） | Phase 5 で挑戦 |
| Gaussian Surfels | 高 | △ | 候補 |
| Marching Cubes (density field) | 低 | ◯ | 不採用（品質不足） |

「まず動かす」を優先し、品質追求は後フェーズに分離する方針。

### 2.3 コリジョン分解について
物理シミュレーションでは**凸形状の組み合わせ**が高速・安定。室内環境の生メッシュは凹形状を含むため、必ず凸分解する。V-HACD と CoACD はいずれも CPU 実装なので gfx1151 に影響しない。

---

## 3. フェーズ別実装計画

### Phase 0: 事前確認（推定 15 min）

**目的**: 入力データの存在確認と環境のセットアップ

```bash
# room3dgs-demo の出力場所確認
ls -la ~/projects/room3dgs-demo/output/
# 期待: *.ply ファイル（Gaussian形式）

# PLY ヘッダ確認 → 3DGS形式かメッシュ形式かを判別
head -30 ~/projects/room3dgs-demo/output/scene.ply
# 期待: scale_*, rot_*, f_dc_*, f_rest_* 等のプロパティが見える → 3DGS確定

# 専用 venv 作成（Genesis World 用とは分離推奨）
python3.12 -m venv ~/venvs/3dgs-mesh
source ~/venvs/3dgs-mesh/bin/activate

# 基本ツール
pip install open3d numpy trimesh plyfile
pip install scikit-image  # marching cubes フォールバック用
```

**完了判定**: 3DGS の PLY が存在し、Open3D が import できる

### Phase 1: メッシュ抽出（推定 1-2 hours）

**目的**: 3D Gaussian の中心点を点群として扱い、Poisson Surface Reconstruction でメッシュ化

```python
# extract_mesh_from_3dgs.py
import open3d as o3d
import numpy as np
from plyfile import PlyData

# 3DGS PLY を読み込み（標準PLYパーサだとガウシアン情報は無視される）
ply = PlyData.read("scene.ply")
v = ply["vertex"]
points = np.stack([v["x"], v["y"], v["z"]], axis=-1)

# Open3D 点群化
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(points)

# ノイズ除去
pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)

# 法線推定（Poisson に必須）
pcd.estimate_normals(
    search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
)
pcd.orient_normals_consistent_tangent_plane(k=20)

# Poisson Surface Reconstruction
mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    pcd, depth=9, width=0, scale=1.1, linear_fit=False
)

# 低密度領域の除去（外周の不要メッシュ削除）
densities = np.asarray(densities)
vertices_to_remove = densities < np.quantile(densities, 0.05)
mesh.remove_vertices_by_mask(vertices_to_remove)

# 出力
o3d.io.write_triangle_mesh("room_mesh.obj", mesh)
print(f"Vertices: {len(mesh.vertices)}, Triangles: {len(mesh.triangles)}")
```

**チューニングパラメータ**:
- `depth=9`: Poisson の深さ（大きいほど高解像度。9-11が部屋スケールの目安）
- `quantile(densities, 0.05)`: 5% 以下の低密度頂点を除去（外周ノイズ対策）
- 法線方向の整合性が品質を左右する → `orient_normals_consistent_tangent_plane` 必須

**完了判定**:
- `room_mesh.obj` が生成される
- MeshLab / Blender で開いて部屋の形状が認識できる
- 頂点数 1万〜10万程度が目安

### Phase 2: メッシュ後処理（推定 30 min）

**目的**: 物理シミュレーション可能な品質に整える

```python
# clean_mesh.py
import trimesh

mesh = trimesh.load("room_mesh.obj")

# 1. 不要小片の除去（最大連結成分のみ残す）
components = mesh.split(only_watertight=False)
mesh = max(components, key=lambda m: len(m.faces))

# 2. デシメーション（面数削減、シミュレーション速度向上）
target_faces = 50000
mesh = mesh.simplify_quadric_decimation(target_faces)

# 3. ホール埋め
trimesh.repair.fill_holes(mesh)

# 4. 法線再計算
mesh.fix_normals()

# 5. スケール確認・正規化
# room3dgs-demo の出力スケールはモデルに依存するので実測してから調整
print(f"Extents: {mesh.extents}")  # 部屋なら数メートル程度を期待
# 必要なら mesh.apply_scale(1.0 / mesh.extents.max() * 5.0) など

mesh.export("room_clean.obj")
```

**完了判定**: 部屋の床・壁が明確に分離でき、面数が 5 万程度まで削減できている

### Phase 3: コリジョン分解（推定 30 min）

**目的**: V-HACD または CoACD で凸分解

```bash
# CoACD インストール（V-HACDより新しく品質良好）
pip install coacd
```

```python
# decompose_collision.py
import coacd
import trimesh

mesh = trimesh.load("room_clean.obj")
mesh_coacd = coacd.Mesh(mesh.vertices, mesh.faces)

# 凸分解実行
parts = coacd.run_coacd(
    mesh_coacd,
    threshold=0.05,      # 大きいほど少ない凸体に分解（高速だが粗い）
    max_convex_hull=64,  # 凸体の最大数
    preprocess_mode="auto"
)

# 各凸体を個別 OBJ として保存
for i, (vertices, faces) in enumerate(parts):
    convex_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    convex_mesh.export(f"room_collision_{i:03d}.obj")

print(f"Decomposed into {len(parts)} convex parts")
```

**注意**: `threshold` を小さくしすぎると凸体数が爆発しシミュレーション速度が落ちる。最初は `threshold=0.05`, `max_convex_hull=64` で試し、必要に応じて調整。

**完了判定**: `room_collision_*.obj` が複数生成される（10〜64個程度）

### Phase 4: Genesis World ロード + Franka 配置（推定 1 hour）

**目的**: 部屋メッシュと Franka を同一シーンに配置し物理動作させる

```python
# room_with_franka.py
import genesis as gs
import glob

gs.init(backend=gs.gpu)

scene = gs.Scene(
    show_viewer=True,
    sim_options=gs.options.SimOptions(dt=0.01),
)

# 1. 部屋の視覚メッシュ（描画用、凸分解前のクリーンメッシュ）
room_visual = scene.add_entity(
    morph=gs.morphs.Mesh(
        file="room_clean.obj",
        fixed=True,             # 静的固定
        collision=False,        # 視覚専用
    ),
)

# 2. 部屋のコリジョン形状（凸分解した複数メッシュ）
for collision_file in sorted(glob.glob("room_collision_*.obj")):
    scene.add_entity(
        morph=gs.morphs.Mesh(
            file=collision_file,
            fixed=True,
            visualization=False,  # コリジョン専用
        ),
    )

# 3. Franka アーム配置
# 部屋の床面 z 座標を事前に確認し、その上に配置
franka = scene.add_entity(
    morph=gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"),
    # Genesis 付属の Franka MJCF を使用
)

scene.build()

# 簡易動作テスト
for i in range(2000):
    scene.step()
```

**ハマりどころ**:
- 床面の z 座標とロボットベース位置の整合性 → Phase 2 でスケール・原点を確認しておくことが重要
- Genesis 付属の Franka MJCF パスは要バージョン確認
- xrdp 経由表示が詰まったら `show_viewer=False` に切り替え、カメラレンダリングを画像保存に変更

**完了判定**: 部屋の中で Franka アームが地面に固定されて見え、関節を動かしてもメッシュにめり込まない

### Phase 5 (optional): SuGaR / 2DGS で品質向上（別タスク化推奨）

**目的**: Poisson より高品質なメッシュを得る

ROCm 移植が必要なため、本 HANDOFF のスコープ外とする。別 HANDOFF として切り出す。

参考リポジトリ:
- SuGaR: <https://github.com/Anttwo/SuGaR>
- 2DGS: <https://github.com/hbb1/2d-gaussian-splatting>
- Gaussian Surfels: <https://github.com/turandai/gaussian_surfels>

---

## 4. 既知の問題 / 注意点

| カテゴリ | 内容 | 対策 |
|---------|------|------|
| スケール | 3DGS の出力はメートル単位とは限らない | Phase 2 で実測 → スケーリング |
| 原点 | 3DGS の原点は撮影開始位置依存 | 必要に応じて床面が z=0 になるよう変換 |
| 法線 | Poisson は法線方向に敏感 | `orient_normals_consistent_tangent_plane` 必須 |
| 床面の品質 | iPhone キャプチャは床面が薄くなりがち | 床面だけ手動で平面メッシュに差し替えも検討 |
| 天井・外部メッシュ | 不要な外周メッシュが残ることが多い | density quantile で除去、または BoundingBox で切り出し |
| シミュレーション速度 | コリジョン凸体数が増えると遅い | `max_convex_hull` で抑制、`threshold` を上げる |
| GUI 表示 | xrdp 経由で OpenGL コンテキスト失敗の可能性 | ヘッドレス + 画像保存にフォールバック |
| Genesis Franka パス | バージョンによって MJCF 配置が異なる | `python -c "import genesis; print(genesis.__path__)"` で実体確認 |

---

## 5. 検証用スクリプト集

### 5.1 中間生成物の可視化
```bash
# Open3D ビューア
python -c "import open3d as o3d; o3d.visualization.draw_geometries([o3d.io.read_triangle_mesh('room_clean.obj')])"

# あるいは MeshLab / Blender で開く
```

### 5.2 シミュレーション動作のキャプチャ
```bash
# Genesis スクリプト実行をビデオキャプチャ
# OBS Studio または ffmpeg + xdpyinfo
ffmpeg -video_size 1920x1080 -framerate 30 -f x11grab -i :0.0 output.mp4
```

---

## 6. 参照リンク

- **Open3D Poisson Reconstruction**: <http://www.open3d.org/docs/latest/tutorial/Advanced/surface_reconstruction.html>
- **CoACD**: <https://github.com/SarahWeiii/CoACD>
- **V-HACD**: <https://github.com/kmammou/v-hacd>
- **trimesh**: <https://trimesh.org/>
- **Genesis World docs**: <https://genesis-world.readthedocs.io/>
- **既存プロジェクト**: `room3dgs-demo` ローカルリポジトリ

---

## 7. 想定アウトプット

- [ ] `room_mesh.obj`（Poisson 再構成メッシュ）
- [ ] `room_clean.obj`（後処理済みメッシュ、5万面程度）
- [ ] `room_collision_*.obj`（凸分解された複数メッシュ）
- [ ] Genesis World 上で部屋＋Franka アームが動作するスクリプト
- [ ] 動作キャプチャ動画（30秒程度）
- [ ] Qiita 記事下書き（Markdown）
- [ ] 全体パイプラインを示す図（draw.io or Mermaid）

---

## 8. 次セッションへの引き継ぎ事項

- 本 HANDOFF で end-to-end が通ったら、**別 HANDOFF として SuGaR / 2DGS の ROCm 移植**を立ち上げる
- ロボットを **Unitree G1 に置き換えた歩行デモ**も後続候補（地面の物理品質要件が上がる）
- 部屋メッシュに **VLM (Nemotron 3 Nano Omni) で意味ラベル**を付与し、Franka が「机の上のコップを取る」のような言語駆動タスクに使う案
- iPhone キャプチャを自動アップロードする仕組み（既存の room3dgs-demo の plugin アーキテクチャを流用）と Genesis 連携のフルパイプライン化
