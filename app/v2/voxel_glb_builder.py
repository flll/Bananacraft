"""Block list → textured GLB バイナリ変換。

1 ブロック = 1 cube (6 quads = 12 三角形)。各面ごとに `vanilla.atlas` で参照される
タイルを、`texture_atlas.build_pixel_atlas` で生成した 320×320 PNG アトラスから
UV マッピングして貼り付ける。隣接ブロックがある面は描画しない（隠面除去）。

trimesh の `TextureVisuals` + `PBRMaterial` を 1 つだけ持つ単一マテリアル GLB を出力し、
`model-viewer` で表示できる軽量バイナリ (典型例: 150 ブロックで ~50KB) を返す。

公開 API:

- `build_voxel_glb(blocks, atlas, atlas_png_path, *, cull_hidden_faces=True) -> bytes`
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import trimesh
from PIL import Image

from voxelizer.block_assigner import BlockAtlas, BlockFace


# ---------------------------------------------------------------------
# Cube geometry
# ---------------------------------------------------------------------

# 立方体 (0,0,0)-(1,1,1) の 8 頂点
_CUBE_VERTS = np.array(
    [
        (0.0, 0.0, 0.0),  # 0
        (1.0, 0.0, 0.0),  # 1
        (1.0, 1.0, 0.0),  # 2
        (0.0, 1.0, 0.0),  # 3
        (0.0, 0.0, 1.0),  # 4
        (1.0, 0.0, 1.0),  # 5
        (1.0, 1.0, 1.0),  # 6
        (0.0, 1.0, 1.0),  # 7
    ],
    dtype=np.float32,
)


# 各面: (face_name, quad_vertex_indices, neighbor_offset)
# quad の頂点順序は CCW (外側から見て反時計回り) で右手系の法線が外向きになる。
# Minecraft 内部座標系: x=east, y=up, z=south (block_assigner と一致)
_FACES: list[tuple[str, tuple[int, int, int, int], tuple[int, int, int]]] = [
    ("up",    (3, 7, 6, 2), (0,  1,  0)),
    ("down",  (0, 1, 5, 4), (0, -1,  0)),
    ("north", (1, 0, 3, 2), (0,  0, -1)),
    ("south", (4, 5, 6, 7), (0,  0,  1)),
    ("east",  (5, 1, 2, 6), (1,  0,  0)),
    ("west",  (0, 4, 7, 3), (-1, 0,  0)),
]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _strip_namespace(block_id: str) -> str:
    """`minecraft:oak_log[axis=y]` → `oak_log` のように states/ns を剥がす。"""
    if not block_id:
        return ""
    if block_id.startswith("minecraft:"):
        block_id = block_id[10:]
    if "[" in block_id:
        block_id = block_id.split("[", 1)[0]
    return block_id


def _resolve_block_atlas_entry(atlas: BlockAtlas, block_type: str):
    """`oak_log` → `atlas.blocks['minecraft:oak_log']` を引く。"""
    key = block_type
    if not key.startswith("minecraft:"):
        key = f"minecraft:{block_type}"
    entry = atlas.get_block(key)
    if entry is not None:
        return entry

    # よくある別名フォールバック: state 付きで来た場合
    base = _strip_namespace(block_type)
    return atlas.get_block(f"minecraft:{base}")


def _face_uv_rect(face: BlockFace, atlas_size: int) -> tuple[float, float, float, float]:
    """1 つの face のアトラス UV 矩形 (u0, v0, u1, v1) を返す。

    GLTF/glb の UV 規約は **左上原点** (V=0 が画像の上)。
    Pillow も上から下に描画しているので row=0 が画像最上行 → V=0 とする。

    タイル境界の bleeding を防ぐため 0.5px 内側にインセットする。
    """
    col = face.atlas_col if face.atlas_col is not None else 0
    row = face.atlas_row if face.atlas_row is not None else 0
    tile = 1.0 / float(atlas_size)
    inset = tile * (0.5 / 16.0)  # 0.5px / 16px tile
    u0 = col * tile + inset
    u1 = (col + 1) * tile - inset
    v0 = row * tile + inset
    v1 = (row + 1) * tile - inset
    return u0, v0, u1, v1


# ---------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------

def build_voxel_glb(
    blocks: Iterable[dict],
    atlas: BlockAtlas,
    atlas_png_path: str | Path,
    *,
    cull_hidden_faces: bool = True,
) -> bytes:
    """block list を 1 つの texturized GLB に変換して bytes を返す。

    Args:
        blocks: ``[{"x": int, "y": int, "z": int, "type": "minecraft:oak_log"}, ...]``
        atlas: 既ロードの ``BlockAtlas`` (per-face texture_name を持つ)
        atlas_png_path: 320×320 ピクセルアトラス PNG のパス
        cull_hidden_faces: 隣接ブロックで隠れる面をスキップするか

    Returns:
        GLB バイナリ。``glTF`` マジックバイトで始まる。
    """
    blocks_list = list(blocks)
    if not blocks_list:
        raise ValueError("blocks is empty")

    atlas_png = Path(atlas_png_path)
    if not atlas_png.exists():
        raise FileNotFoundError(f"atlas PNG not found: {atlas_png}")

    # 1. 占有マップ (cull 用)
    occupied: set[tuple[int, int, int]] = set()
    if cull_hidden_faces:
        for b in blocks_list:
            occupied.add((int(b["x"]), int(b["y"]), int(b["z"])))

    atlas_size = atlas.atlas_size

    # 2. 各面を頂点 / 三角形 / UV に展開
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    uvs: list[tuple[float, float]] = []

    for b in blocks_list:
        bx, by, bz = int(b["x"]), int(b["y"]), int(b["z"])
        block_type = b.get("type", "stone")
        entry = _resolve_block_atlas_entry(atlas, block_type)
        if entry is None:
            entry = _resolve_block_atlas_entry(atlas, "minecraft:stone")
        if entry is None:
            continue  # アトラス自体が壊れている場合のみスキップ

        for face_name, quad_idx, neighbor in _FACES:
            if cull_hidden_faces:
                neighbor_pos = (bx + neighbor[0], by + neighbor[1], bz + neighbor[2])
                if neighbor_pos in occupied:
                    continue

            face_meta = entry.faces.get(face_name)
            if face_meta is None:
                continue

            u0, v0, u1, v1 = _face_uv_rect(face_meta, atlas_size)
            base = len(verts)
            quad_world_verts = []
            for vidx in quad_idx:
                vx, vy, vz = _CUBE_VERTS[vidx]
                quad_world_verts.append((bx + vx, by + vy, bz + vz))
            verts.extend(quad_world_verts)

            # quad の 4 頂点 → UV (左下→右下→右上→左上)
            # GLTF の V は上方向に増える系もあるが、Pillow 経由の PNG とは
            # Pillow が画像を上から下に書いている → V を反転して整合させる
            uvs.extend([
                (u0, 1.0 - v1),  # 左下
                (u1, 1.0 - v1),  # 右下
                (u1, 1.0 - v0),  # 右上
                (u0, 1.0 - v0),  # 左上
            ])

            faces.append((base + 0, base + 1, base + 2))
            faces.append((base + 0, base + 2, base + 3))

    if not faces:
        raise ValueError("no faces to render (all culled?)")

    vertices = np.asarray(verts, dtype=np.float32)
    face_array = np.asarray(faces, dtype=np.int32)
    uv_array = np.asarray(uvs, dtype=np.float32)

    # 3. テクスチャ & マテリアル
    texture_image = Image.open(atlas_png).convert("RGBA")
    material = trimesh.visual.material.PBRMaterial(
        name="bananacraft_pixel_atlas",
        baseColorTexture=texture_image,
        metallicFactor=0.0,
        roughnessFactor=1.0,
        # `model-viewer` で sRGB 解釈を素直にするための明示
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
    )
    visual = trimesh.visual.TextureVisuals(uv=uv_array, material=material)

    # 4. Mesh 構築 & GLB 化
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=face_array,
        visual=visual,
        process=False,
    )
    scene = trimesh.Scene([mesh])
    return scene.export(file_type="glb")


__all__ = ["build_voxel_glb"]
