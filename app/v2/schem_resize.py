"""``.schem`` の外接サイズ調整とブロック種置換（Phase 3 / Bloxelizer parity）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from v2.schem_preview import SchemPreviewError, parse_schem_blocks, schem_dimensions
from v2.schem_writer import write_schem_from_blocks


def _block_base(block_id: str) -> str:
    return str(block_id).split("[", 1)[0]


def scale_blocks_to_footprint(
    blocks: List[Dict[str, Any]],
    target_footprint: int,
    *,
    tolerance: float = 1.5,
) -> Tuple[List[Dict[str, Any]], bool]:
    """ゾーン最長辺に合わせて X/Z を均一スケール。戻り値: (blocks, was_scaled)。"""
    if not blocks or target_footprint <= 0:
        return blocks, False
    w = max(int(b["x"]) for b in blocks) + 1
    d = max(int(b["z"]) for b in blocks) + 1
    longest = max(w, d)
    if longest <= 0 or longest <= target_footprint * tolerance:
        return blocks, False
    scale = float(target_footprint) / float(longest)
    merged: Dict[Tuple[int, int, int], str] = {}
    for b in blocks:
        nx = int(round(int(b["x"]) * scale))
        ny = int(round(int(b["y"]) * scale))
        nz = int(round(int(b["z"]) * scale))
        merged[(nx, ny, nz)] = str(b.get("type") or "minecraft:stone")
    out = [{"x": x, "y": y, "z": z, "type": t} for (x, y, z), t in merged.items()]
    return out, True


def auto_resize_schem_file(
    path: str | Path,
    zone_width: int,
    zone_depth: int,
    *,
    tolerance: float = 1.5,
) -> bool:
    """過大な schem をゾーン最長辺にリサイズして上書き。変更時 True。"""
    target = max(int(zone_width), int(zone_depth))
    p = Path(path)
    if not p.is_file() or target <= 0:
        return False
    blocks = parse_schem_blocks(p, skip_air=True)
    scaled, was = scale_blocks_to_footprint(blocks, target, tolerance=tolerance)
    if not was:
        return False
    write_schem_from_blocks(scaled, p)
    return True


def replace_block_type_in_schem(
    path: str | Path,
    from_block: str,
    to_block: str,
) -> int:
    """schem 内のブロック種を一括置換。置換数を返す。"""
    p = Path(path)
    if not p.is_file():
        raise SchemPreviewError(f"ファイルがありません: {p}")
    src = _block_base(from_block)
    dst = str(to_block)
    blocks = parse_schem_blocks(p, skip_air=False)
    count = 0
    for b in blocks:
        if _block_base(b.get("type", "")) == src:
            b["type"] = dst
            count += 1
    if count == 0:
        return 0
    write_schem_from_blocks(blocks, p)
    return count


def footprint_mismatch_ratio(path: str | Path, zone_width: int, zone_depth: int) -> float:
    """schem 最長辺 / ゾーン最長辺。1.0 以下なら収まっている。"""
    w, _h, l = schem_dimensions(path)
    target = max(int(zone_width), int(zone_depth))
    if target <= 0:
        return 0.0
    return max(w, l) / float(target)


__all__ = [
    "auto_resize_schem_file",
    "footprint_mismatch_ratio",
    "replace_block_type_in_schem",
    "scale_blocks_to_footprint",
]
