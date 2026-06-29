"""blocks 列から Sponge Schematic v2 (``.schem``) を書き出す。

Path B（ローカル GLB ボクセル化）の成果物を WorldEdit 配置可能な形式にする。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import nbtlib
    from nbtlib import ByteArray, Compound, File, Int, List as NbtList, Short
except ImportError:  # pragma: no cover
    nbtlib = None  # type: ignore[assignment]

from v2.schem_preview import SchemPreviewError


def _require_nbtlib() -> None:
    if nbtlib is None:
        raise SchemPreviewError(
            "schem 書き出しには nbtlib が必要です。`pip install nbtlib` 後に再起動してください。"
        )


def _encode_varints(values: List[int]) -> bytes:
    out = bytearray()
    for value in values:
        v = int(value)
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def _normalize_blocks(
    blocks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int, int, int]:
    if not blocks:
        raise SchemPreviewError("書き出すブロックがありません")
    min_x = min(int(b["x"]) for b in blocks)
    min_y = min(int(b["y"]) for b in blocks)
    min_z = min(int(b["z"]) for b in blocks)
    norm: List[Dict[str, Any]] = []
    for b in blocks:
        norm.append(
            {
                "x": int(b["x"]) - min_x,
                "y": int(b["y"]) - min_y,
                "z": int(b["z"]) - min_z,
                "type": str(b.get("type") or "minecraft:stone"),
            }
        )
    max_x = max(b["x"] for b in norm)
    max_y = max(b["y"] for b in norm)
    max_z = max(b["z"] for b in norm)
    return norm, max_x + 1, max_y + 1, max_z + 1


def write_schem_from_blocks(
    blocks: List[Dict[str, Any]],
    path: str | Path,
    *,
    data_version: int = 3465,
) -> Path:
    """``blocks_v2`` 互換 dict 列から gzip 圧縮 ``.schem`` を書き出す。"""
    _require_nbtlib()
    norm, width, height, length = _normalize_blocks(blocks)

    palette_names = sorted({b["type"] for b in norm})
    if "minecraft:air" not in palette_names:
        palette_names = ["minecraft:air"] + palette_names
    name_to_id = {name: i for i, name in enumerate(palette_names)}
    air_id = name_to_id["minecraft:air"]

    total = width * height * length
    indices = [air_id] * total
    for b in norm:
        x, y, z = b["x"], b["y"], b["z"]
        idx = x + z * width + y * width * length
        if 0 <= idx < total:
            indices[idx] = name_to_id.get(b["type"], air_id)

    palette = Compound({name: Int(pid) for name, pid in name_to_id.items()})
    root = Compound(
        {
            "Version": Int(2),
            "DataVersion": Int(data_version),
            "Width": Short(width),
            "Height": Short(height),
            "Length": Short(length),
            "Palette": palette,
            "BlockData": ByteArray(list(_encode_varints(indices))),
            "BlockEntities": NbtList[Compound]([]),
        }
    )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    File(root).save(str(out), gzipped=True)
    return out


def assigned_blocks_to_dicts(assigned) -> List[Dict[str, Any]]:
    """``AssignedBlock`` 列を blocks_v2 形式に変換。"""
    out: List[Dict[str, Any]] = []
    for ab in assigned:
        x, y, z = ab.position
        block_id = ab.get_full_block_id() if hasattr(ab, "get_full_block_id") else ab.block_name
        out.append({"x": int(x), "y": int(y), "z": int(z), "type": str(block_id)})
    return out


__all__ = [
    "assigned_blocks_to_dicts",
    "write_schem_from_blocks",
]
