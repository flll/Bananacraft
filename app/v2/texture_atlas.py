"""Pixel atlas PNG generator (公式 jar 優先 + 手作りフォールバック)。

優先順位:

1. **公式アトラス** (``build_official_atlas``)
   - ``mc_assets.ensure_official_assets()`` が Mojang client.jar から抽出した
     ``assets/minecraft/textures/block/*.png`` を、``vanilla.atlas`` の
     ``atlasColumn/atlasRow`` 座標に従って 1 枚の 320×320 PNG にリパックする。
   - 各 PNG は 16×16 が標準。それ以外は NEAREST でリサイズ。
   - アニメ PNG (縦に複数フレーム) は先頭フレームだけ使う。
2. **手作りアトラス** (``build_pixel_atlas``)
   - jar が無い・ネットワーク不通時のフォールバック。
   - atlas の base color + 決定論的ノイズで Minecraft 風タイルを生成。

公開 API:

- ``build_pixel_atlas(atlas_data, tile_px=16)``  --- 手作り
- ``build_official_atlas(atlas_data, textures, tile_px=16)``  --- 公式 PNG リパック
- ``get_or_build_atlas_png(atlas, force_procedural=False)`` --- 自動選択
- ``get_atlas_provenance()`` --- 直近に生成されたアトラスの種類 (キャッシュキー用)
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from voxelizer.block_assigner import BlockAtlas


logger = logging.getLogger(__name__)


_CACHE_DIR = Path.home() / ".cache" / "bananacraft"
_PROCEDURAL_CACHE_PATH = _CACHE_DIR / "voxel_atlas_procedural.png"
_PROVENANCE_PATH = _CACHE_DIR / "voxel_atlas.provenance"
# 現プロセス内での provenance (Streamlit cache_data のキーにも使う)
_LAST_PROVENANCE: str = "unknown"


# ---------------------------------------------------------------------
# Procedural (手作り)
# ---------------------------------------------------------------------


def _hash_noise(tex_name: str, x: int, y: int) -> float:
    """テクスチャ名 + 座標から決定論的にノイズ値 [-1, 1] を返す。"""
    key = f"{tex_name}:{x}:{y}".encode("utf-8")
    h = hashlib.blake2b(key, digest_size=2).digest()
    return (int.from_bytes(h, "big") / 32767.5) - 1.0


def _render_tile(
    tex_name: str,
    base_rgb: tuple[float, float, float],
    std: float,
    tile_px: int,
) -> np.ndarray:
    tile = np.zeros((tile_px, tile_px, 4), dtype=np.float32)
    base = np.array(base_rgb, dtype=np.float32)
    amp = max(0.02, min(0.25, float(std) * 0.6))

    for y in range(tile_px):
        for x in range(tile_px):
            noise = _hash_noise(tex_name, x, y) * amp
            rgb = np.clip(base + noise, 0.0, 1.0)
            tile[y, x, 0:3] = rgb
            tile[y, x, 3] = 1.0

    border = 0.88
    tile[0, :, 0:3] *= border
    tile[-1, :, 0:3] *= border
    tile[:, 0, 0:3] *= border
    tile[:, -1, 0:3] *= border

    return (tile * 255).astype(np.uint8)


def build_pixel_atlas(atlas_data: dict, tile_px: int = 16) -> Image.Image:
    """手作りピクセルアトラス: atlas base color + ノイズで Minecraft 風タイル。

    Returns:
        ``(atlas_size * tile_px)`` 角の RGBA PIL.Image。
    """
    atlas_size = int(atlas_data.get("atlasSize", 20))
    textures: dict = atlas_data.get("textures", {}) or {}
    canvas_px = atlas_size * tile_px

    canvas = np.full((canvas_px, canvas_px, 4), [255, 0, 255, 255], dtype=np.uint8)

    for tex_name, tex in textures.items():
        if not isinstance(tex, dict):
            continue
        col = tex.get("atlasColumn")
        row = tex.get("atlasRow")
        if col is None or row is None:
            continue
        col = int(col)
        row = int(row)
        if not (0 <= col < atlas_size and 0 <= row < atlas_size):
            continue

        col_info = tex.get("colour") or {}
        rgb = (
            float(col_info.get("r", 0.5)),
            float(col_info.get("g", 0.5)),
            float(col_info.get("b", 0.5)),
        )
        std = float(tex.get("std", 0.0))

        tile = _render_tile(tex_name, rgb, std, tile_px)
        y0 = row * tile_px
        x0 = col * tile_px
        canvas[y0 : y0 + tile_px, x0 : x0 + tile_px] = tile

    return Image.fromarray(canvas, mode="RGBA")


# ---------------------------------------------------------------------
# Official (公式 jar の PNG をリパック)
# ---------------------------------------------------------------------


def _load_first_frame(png_path: Path, tile_px: int) -> Optional[np.ndarray]:
    """公式 PNG を 1 タイル分 (tile_px x tile_px x 4) に正規化。

    - アニメ PNG (縦に複数フレーム = 高さ % 幅 == 0 && 高さ > 幅) は先頭フレームのみ
    - 16px 以外は NEAREST でリサイズしてピクセルアートらしさを保つ
    - 失敗時は None
    """
    try:
        img = Image.open(png_path).convert("RGBA")
    except (OSError, ValueError):
        logger.debug("failed to read %s", png_path, exc_info=True)
        return None

    w, h = img.size
    if w == 0 or h == 0:
        return None

    # アニメ PNG: 高さが幅の整数倍 & 高さ > 幅 → 先頭フレームを切り出す
    if h > w and h % w == 0:
        img = img.crop((0, 0, w, w))
        h = w

    if (w, h) != (tile_px, tile_px):
        img = img.resize((tile_px, tile_px), Image.Resampling.NEAREST)

    arr = np.asarray(img, dtype=np.uint8)
    if arr.shape != (tile_px, tile_px, 4):
        return None
    return arr


def build_official_atlas(
    atlas_data: dict,
    textures: dict[str, Path],
    tile_px: int = 16,
) -> Image.Image:
    """公式 client.jar から抽出した PNG を 1 枚にリパック。

    Args:
        atlas_data: vanilla.atlas を JSON 読み込みした辞書。
        textures: ``{"minecraft:block/oak_log": Path(..png), ...}``。
        tile_px: 1 タイルの辺サイズ (px)。既定 16。

    Returns:
        ``(atlas_size * tile_px)`` 角の RGBA PIL.Image。不足タイルはマゼンタで埋める。
    """
    atlas_size = int(atlas_data.get("atlasSize", 20))
    atlas_textures: dict = atlas_data.get("textures", {}) or {}
    canvas_px = atlas_size * tile_px

    canvas = np.full((canvas_px, canvas_px, 4), [255, 0, 255, 255], dtype=np.uint8)
    placed = 0
    missing: list[str] = []

    for tex_name, tex in atlas_textures.items():
        if not isinstance(tex, dict):
            continue
        col = tex.get("atlasColumn")
        row = tex.get("atlasRow")
        if col is None or row is None:
            continue
        col = int(col)
        row = int(row)
        if not (0 <= col < atlas_size and 0 <= row < atlas_size):
            continue

        png_path = textures.get(tex_name)
        if png_path is None or not png_path.exists():
            missing.append(tex_name)
            continue

        tile_arr = _load_first_frame(png_path, tile_px)
        if tile_arr is None:
            missing.append(tex_name)
            continue

        y0 = row * tile_px
        x0 = col * tile_px
        canvas[y0 : y0 + tile_px, x0 : x0 + tile_px] = tile_arr
        placed += 1

    if missing:
        logger.info(
            "official atlas: placed=%d, missing=%d (first 5: %s)",
            placed,
            len(missing),
            missing[:5],
        )

    return Image.fromarray(canvas, mode="RGBA")


# ---------------------------------------------------------------------
# Cache orchestration
# ---------------------------------------------------------------------


def _official_cache_path(version: str) -> Path:
    safe_ver = "".join(c for c in version if c.isalnum() or c in {".", "-", "_"})
    return _CACHE_DIR / f"voxel_atlas_official_{safe_ver}.png"


def _write_provenance(value: str) -> None:
    global _LAST_PROVENANCE
    _LAST_PROVENANCE = value
    try:
        _PROVENANCE_PATH.write_text(value, encoding="utf-8")
    except OSError:
        pass


def get_atlas_provenance() -> str:
    """直近に呼ばれた ``get_or_build_atlas_png`` がどちらを返したか。

    Returns:
        ``"official:<version>"`` か ``"procedural"`` か ``"unknown"`` (未呼出時)。
    """
    if _LAST_PROVENANCE != "unknown":
        return _LAST_PROVENANCE
    try:
        if _PROVENANCE_PATH.exists():
            return _PROVENANCE_PATH.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        pass
    return "unknown"


def get_or_build_atlas_png(
    atlas: "BlockAtlas",
    tile_px: int = 16,
    *,
    force_procedural: bool = False,
) -> Path:
    """ピクセルアトラス PNG のパスを返す (キャッシュ込み)。

    優先順:

    1. ``force_procedural=False`` かつ ``mc_assets.ensure_official_assets()``
       が成功した場合は **公式 PNG リパック**を試行。
    2. 失敗時は **手作りアトラス**にフォールバック。

    キャッシュは公式 / 手作り別ファイルに分離して両方残す。サイドカー
    (.mtime ファイル) で atlas mtime + tile_px の組をハッシュ確認する。
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        atlas_mtime = os.path.getmtime(atlas.atlas_path)
    except OSError:
        atlas_mtime = 0.0

    if not force_procedural:
        official = _try_build_official(atlas, atlas_mtime, tile_px=tile_px)
        if official is not None:
            return official

    return _build_procedural(atlas, atlas_mtime, tile_px=tile_px)


def _try_build_official(
    atlas: "BlockAtlas",
    atlas_mtime: float,
    *,
    tile_px: int,
) -> Optional[Path]:
    """公式 jar 経由のアトラスを生成。失敗 (jar 不在 等) なら None。"""
    try:
        from v2 import mc_assets
    except ImportError:
        return None

    info = mc_assets.ensure_official_assets()
    if not info:
        return None
    version = info.get("version")
    textures = info.get("textures") or {}
    if not version or not textures:
        return None

    out_path = _official_cache_path(version)
    stamp_path = out_path.with_suffix(".mtime")
    expected_stamp = f"official:{version}:{atlas_mtime:.6f}:{tile_px}:{len(textures)}"

    cache_valid = False
    if out_path.exists() and stamp_path.exists():
        try:
            cache_valid = (
                stamp_path.read_text(encoding="utf-8").strip() == expected_stamp
                and out_path.stat().st_size > 0
            )
        except OSError:
            cache_valid = False

    if not cache_valid:
        try:
            img = build_official_atlas(atlas.raw_data, textures, tile_px=tile_px)
            img.save(out_path, format="PNG")
            try:
                stamp_path.write_text(expected_stamp, encoding="utf-8")
            except OSError:
                pass
        except Exception:  # noqa: BLE001 - 公式生成失敗時もフォールバックへ
            logger.warning("build_official_atlas failed", exc_info=True)
            return None

    # 古いバージョンのキャッシュを掃除
    try:
        for sibling in _CACHE_DIR.glob("voxel_atlas_official_*.png"):
            if sibling != out_path:
                sibling.unlink(missing_ok=True)
                sibling.with_suffix(".mtime").unlink(missing_ok=True)
    except OSError:
        pass

    _write_provenance(f"official:{version}")
    return out_path


def _build_procedural(
    atlas: "BlockAtlas",
    atlas_mtime: float,
    *,
    tile_px: int,
) -> Path:
    """手作りアトラス (フォールバック) を生成 or キャッシュから返す。"""
    out_path = _PROCEDURAL_CACHE_PATH
    stamp_path = out_path.with_suffix(".mtime")
    expected_stamp = f"procedural:{atlas_mtime:.6f}:{tile_px}"

    cache_valid = False
    if out_path.exists() and stamp_path.exists():
        try:
            cache_valid = (
                stamp_path.read_text(encoding="utf-8").strip() == expected_stamp
                and out_path.stat().st_size > 0
            )
        except OSError:
            cache_valid = False

    if not cache_valid:
        img = build_pixel_atlas(atlas.raw_data, tile_px=tile_px)
        img.save(out_path, format="PNG")
        try:
            stamp_path.write_text(expected_stamp, encoding="utf-8")
        except OSError:
            pass

    _write_provenance("procedural")
    return out_path


__all__ = [
    "build_pixel_atlas",
    "build_official_atlas",
    "get_or_build_atlas_png",
    "get_atlas_provenance",
]
