"""Minecraft ブロック ID → 公式 jar PNG テクスチャ解決。

schem プレビュー用。``vanilla.atlas`` 未登録ブロックも jar 直引き・近似代用で
6 面すべてを埋める（透明穴ゼロ）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from voxelizer.block_assigner import BlockAtlas

FACE_NAMES = ("up", "down", "north", "south", "east", "west")

# block stem → 代用 stem（jar 内 PNG 名）
_SUBSTITUTE_STEMS: Dict[str, str] = {
    "jack_o_lantern": "pumpkin",
    "carved_pumpkin": "pumpkin",
    "bee_nest": "hay_block",
    "beehive": "hay_block",
    "chiseled_bookshelf": "bookshelf",
}

_WOOD_PREFIXES = (
    "oak",
    "spruce",
    "birch",
    "jungle",
    "acacia",
    "dark_oak",
    "cherry",
    "mangrove",
    "crimson",
    "warped",
)


def _strip_block_id(block_id: str) -> str:
    """``minecraft:oak_log[axis=y]`` → ``oak_log``."""
    if not block_id:
        return ""
    if block_id.startswith("minecraft:"):
        block_id = block_id[10:]
    if "[" in block_id:
        block_id = block_id.split("[", 1)[0]
    return block_id


def _jar_key(stem: str) -> str:
    return f"minecraft:block/{stem}"


def _lookup_jar(jar_textures: Dict[str, Path], stem: str) -> Optional[Path]:
    p = jar_textures.get(_jar_key(stem))
    if p is not None and p.is_file():
        return p
    return None


def _face_stems_for_block(stem: str) -> Dict[str, str]:
    """MC ブロック面 → jar PNG stem。"""
    if stem == "grass_block":
        return {
            "up": "grass_block_top",
            "down": "dirt",
            "north": "grass_block_side",
            "south": "grass_block_side",
            "east": "grass_block_side",
            "west": "grass_block_side",
        }
    if stem.endswith("_log"):
        top = f"{stem}_top"
        return {f: top if f in ("up", "down") else stem for f in FACE_NAMES}
    return {f: stem for f in FACE_NAMES}


def _resolve_stem_to_path(
    stem: str,
    jar_textures: Dict[str, Path],
) -> Optional[Path]:
    """1 stem を jar から解決。近似チェーン付き。"""
    candidates = [stem]
    sub = _SUBSTITUTE_STEMS.get(stem)
    if sub:
        candidates.append(sub)
    if stem.endswith("_leaves"):
        candidates.append("oak_leaves")
    if stem.endswith("_stairs") or stem.endswith("_slab"):
        candidates.append(stem.rsplit("_", 1)[0])
    if stem.endswith("_fence") or stem.endswith("_wall"):
        for prefix in _WOOD_PREFIXES:
            if stem.startswith(prefix):
                candidates.append(f"{prefix}_planks")
                break
    candidates.append("stone")

    seen: set[str] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        p = _lookup_jar(jar_textures, c)
        if p is not None:
            return p
    return _lookup_jar(jar_textures, "stone")


@dataclass
class ResolvedFaceTextures:
    """6 面の PNG パス（必ず全 face が存在）。"""

    up: Path
    down: Path
    north: Path
    south: Path
    east: Path
    west: Path
    source: str  # atlas | jar | substitute | fallback

    def as_dict(self) -> Dict[str, Path]:
        return {
            "up": self.up,
            "down": self.down,
            "north": self.north,
            "south": self.south,
            "east": self.east,
            "west": self.west,
        }


def resolve_block_faces(
    block_id: str,
    *,
    atlas: Optional[BlockAtlas] = None,
    jar_textures: Dict[str, Path],
) -> ResolvedFaceTextures:
    """ブロック ID の 6 面テクスチャを解決する。必ず stone 以上で全 face を返す。"""
    stem = _strip_block_id(block_id)
    face_stems = _face_stems_for_block(stem)
    source = "jar"

    # BlockAtlas は参照のみ（jar 優先）。将来 atlas PNG 座標連携用。
    if atlas is not None:
        key = block_id if block_id.startswith("minecraft:") else f"minecraft:{stem}"
        if atlas.get_block(key) is not None:
            source = "atlas"

    faces: Dict[str, Path] = {}
    for fname in FACE_NAMES:
        fstem = face_stems[fname]
        p = _resolve_stem_to_path(fstem, jar_textures)
        if p is None:
            p = _resolve_stem_to_path("stone", jar_textures)
            source = "fallback"
        elif fstem != stem and fstem not in (face_stems.get("up", ""),):
            if source == "atlas":
                source = "substitute"
        faces[fname] = p

    stone = _resolve_stem_to_path("stone", jar_textures)
    if stone is None:
        raise FileNotFoundError("jar textures missing even stone.png")

    for fname in FACE_NAMES:
        if fname not in faces or not faces[fname].is_file():
            faces[fname] = stone
            source = "fallback"

    return ResolvedFaceTextures(
        up=faces["up"],
        down=faces["down"],
        north=faces["north"],
        south=faces["south"],
        east=faces["east"],
        west=faces["west"],
        source=source,
    )


__all__ = [
    "ResolvedFaceTextures",
    "resolve_block_faces",
    "FACE_NAMES",
]
