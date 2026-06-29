"""Sponge ``.schem`` ブロック列 → 公式 jar テクスチャ付き GLB。

``block_texture_resolver`` で面 PNG を解決し、動的アトラスにパックして
``model-viewer`` 用 GLB を返す。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import numpy as np
import trimesh
from PIL import Image

from v2.block_texture_resolver import FACE_NAMES, resolve_block_faces
from voxelizer.block_assigner import BlockAtlas

_CUBE_VERTS = np.array(
    [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    ],
    dtype=np.float32,
)

_FACES: list[tuple[str, tuple[int, int, int, int], tuple[int, int, int]]] = [
    ("up", (3, 7, 6, 2), (0, 1, 0)),
    ("down", (0, 1, 5, 4), (0, -1, 0)),
    ("north", (1, 0, 3, 2), (0, 0, -1)),
    ("south", (4, 5, 6, 7), (0, 0, 1)),
    ("east", (5, 1, 2, 6), (1, 0, 0)),
    ("west", (0, 4, 7, 3), (-1, 0, 0)),
]

TILE_PX = 16


def _load_tile(path: Path, tile_px: int = TILE_PX) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if h > w and h % w == 0:
        img = img.crop((0, 0, w, w))
    if img.size != (tile_px, tile_px):
        img = img.resize((tile_px, tile_px), Image.Resampling.NEAREST)
    return np.asarray(img, dtype=np.uint8)


def _face_uv_rect(col: int, row: int, grid_size: int) -> tuple[float, float, float, float]:
    tile = 1.0 / float(grid_size)
    inset = tile * (0.5 / float(TILE_PX))
    u0 = col * tile + inset
    u1 = (col + 1) * tile - inset
    v0 = row * tile + inset
    v1 = (row + 1) * tile - inset
    return u0, v0, u1, v1


def build_schem_glb(
    blocks: Iterable[dict],
    jar_textures: Dict[str, Path],
    *,
    atlas: BlockAtlas | None = None,
    cull_hidden_faces: bool = True,
) -> bytes:
    """schem ブロック列から jar テクスチャ付き GLB bytes を生成する。"""
    blocks_list = list(blocks)
    if not blocks_list:
        raise ValueError("blocks is empty")

    stone_path = jar_textures.get("minecraft:block/stone")
    if stone_path is None or not Path(stone_path).is_file():
        for v in jar_textures.values():
            if Path(v).is_file():
                stone_path = v
                break
    if stone_path is None:
        raise FileNotFoundError("no jar textures available")

    unique_blocks: Set[str] = {b.get("type", "minecraft:stone") for b in blocks_list}

    face_paths: Dict[Tuple[str, str], Path] = {}
    for bid in unique_blocks:
        resolved = resolve_block_faces(bid, atlas=atlas, jar_textures=jar_textures)
        for fname in FACE_NAMES:
            face_paths[(bid, fname)] = resolved.as_dict()[fname]

    unique_path_keys: List[str] = []
    for p in face_paths.values():
        key = str(Path(p).resolve())
        if key not in unique_path_keys:
            unique_path_keys.append(key)

    n_tiles = len(unique_path_keys)
    grid_size = max(1, math.ceil(math.sqrt(n_tiles)))

    path_to_tile: Dict[str, Tuple[int, int]] = {}
    for idx, key in enumerate(unique_path_keys):
        path_to_tile[key] = (idx % grid_size, idx // grid_size)

    tile_assign: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for (bid, fname), p in face_paths.items():
        tile_assign[(bid, fname)] = path_to_tile[str(Path(p).resolve())]

    canvas_px = grid_size * TILE_PX
    canvas = np.zeros((canvas_px, canvas_px, 4), dtype=np.uint8)
    canvas[:, :, 3] = 255
    for idx, key in enumerate(unique_path_keys):
        col, row = idx % grid_size, idx // grid_size
        tile = _load_tile(Path(key))
        y0, x0 = row * TILE_PX, col * TILE_PX
        canvas[y0 : y0 + TILE_PX, x0 : x0 + TILE_PX] = tile

    atlas_image = Image.fromarray(canvas, mode="RGBA")

    occupied: set[tuple[int, int, int]] = set()
    if cull_hidden_faces:
        for b in blocks_list:
            occupied.add((int(b["x"]), int(b["y"]), int(b["z"])))

    stone_tile = path_to_tile.get(str(Path(stone_path).resolve()), (0, 0))

    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    uvs: list[tuple[float, float]] = []

    for b in blocks_list:
        bx, by, bz = int(b["x"]), int(b["y"]), int(b["z"])
        block_type = b.get("type", "minecraft:stone")

        for face_name, quad_idx, neighbor in _FACES:
            if cull_hidden_faces:
                npos = (bx + neighbor[0], by + neighbor[1], bz + neighbor[2])
                if npos in occupied:
                    continue

            col, row = tile_assign.get((block_type, face_name), stone_tile)
            u0, v0, u1, v1 = _face_uv_rect(col, row, grid_size)
            base = len(verts)
            for vidx in quad_idx:
                vx, vy, vz = _CUBE_VERTS[vidx]
                verts.append((bx + vx, by + vy, bz + vz))
            uvs.extend([
                (u0, 1.0 - v1),
                (u1, 1.0 - v1),
                (u1, 1.0 - v0),
                (u0, 1.0 - v0),
            ])
            faces.append((base + 0, base + 1, base + 2))
            faces.append((base + 0, base + 2, base + 3))

    if not faces:
        raise ValueError("no faces to render (all culled?)")

    vertices = np.asarray(verts, dtype=np.float32)
    face_array = np.asarray(faces, dtype=np.int32)
    uv_array = np.asarray(uvs, dtype=np.float32)

    material = trimesh.visual.material.PBRMaterial(
        name="bananacraft_schem_atlas",
        baseColorTexture=atlas_image,
        metallicFactor=0.0,
        roughnessFactor=1.0,
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
    )
    visual = trimesh.visual.TextureVisuals(uv=uv_array, material=material)
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=face_array,
        visual=visual,
        process=False,
    )
    scene = trimesh.Scene([mesh])
    return scene.export(file_type="glb")


__all__ = ["build_schem_glb"]
