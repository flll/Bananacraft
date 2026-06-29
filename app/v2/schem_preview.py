"""Sponge Schematic (``.schem``) を Streamlit プレビュー用に読み込む。

WorldEdit 配置とは独立した軽量解析。Tripo schem 経路で ``blocks_v2.json`` が
無い場合に Plotly / GLB プレビューを表示するために使う。
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import nbtlib
except ImportError:  # pragma: no cover - requirements.txt に nbtlib を追加
    nbtlib = None  # type: ignore[assignment]


class SchemPreviewError(Exception):
    """``.schem`` の読み込み・解析に失敗したとき。"""


def _require_nbtlib():
    if nbtlib is None:
        raise SchemPreviewError(
            "schem プレビューには nbtlib が必要です。"
            " `pip install nbtlib` 後にアプリを再起動してください。"
        )


def _decode_varints(data: bytes) -> List[int]:
    """Sponge Schematic v2 の BlockData (varint 列) をデコードする。"""
    out: List[int] = []
    i = 0
    n = len(data)
    while i < n:
        value = 0
        shift = 0
        while True:
            if i >= n:
                break
            b = data[i]
            i += 1
            value |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
            if shift > 35:
                raise SchemPreviewError("BlockData の varint が不正です")
        out.append(value)
    return out


def _is_air(block_id: str) -> bool:
    base = block_id.split("[", 1)[0]
    return base.endswith(":air") or base == "air"


def _load_nbt(path: Path):
    _require_nbtlib()
    try:
        return nbtlib.load(str(path))
    except OSError as e:
        raise SchemPreviewError(f".schem を開けません: {path}") from e
    except Exception as e:  # noqa: BLE001 - nbtlib の多様な失敗を 1 つにまとめる
        raise SchemPreviewError(f".schem の NBT 解析に失敗: {e}") from e


def schem_dimensions(path: str | Path) -> Tuple[int, int, int]:
    """(width, height, length) を返す。"""
    nbt = _load_nbt(Path(path))
    return int(nbt["Width"]), int(nbt["Height"]), int(nbt["Length"])


def schem_palette_counts(path: str | Path, *, top_n: int = 12) -> List[Tuple[str, int]]:
    """ブロック種ごとの出現回数 Top N（air 除く）。"""
    nbt = _load_nbt(Path(path))
    palette = {int(v): str(k) for k, v in nbt["Palette"].items()}
    indices = _decode_varints(bytes(nbt["BlockData"]))
    counts = Counter(
        palette.get(i, "?").split("[", 1)[0]
        for i in indices
        if not _is_air(palette.get(i, "minecraft:air"))
    )
    return counts.most_common(top_n)


def parse_schem_blocks(
    path: str | Path,
    *,
    skip_air: bool = True,
    max_blocks: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Sponge v2 ``.schem`` を ``blocks_v2`` 互換の dict 列に変換する。

    Block 並び順は Sponge v2 仕様どおり x → z → y（x が最速）。
    """
    nbt = _load_nbt(Path(path))
    width = int(nbt["Width"])
    height = int(nbt["Height"])
    length = int(nbt["Length"])

    palette = {int(v): str(k) for k, v in nbt["Palette"].items()}
    indices = _decode_varints(bytes(nbt["BlockData"]))
    expected = width * height * length
    if len(indices) != expected:
        raise SchemPreviewError(
            f"BlockData 長不一致: got {len(indices)}, expected {expected}"
        )

    blocks: List[Dict[str, Any]] = []
    idx = 0
    for y in range(height):
        for z in range(length):
            for x in range(width):
                block_type = palette.get(indices[idx], "minecraft:air")
                idx += 1
                if skip_air and _is_air(block_type):
                    continue
                blocks.append({"x": x, "y": y, "z": z, "type": block_type})
                if max_blocks is not None and len(blocks) >= max_blocks:
                    return blocks
    return blocks


def schem_summary(path: str | Path) -> Dict[str, Any]:
    """プレビュー UI 用のメタ情報。"""
    p = Path(path)
    width, height, length = schem_dimensions(p)
    top = schem_palette_counts(p)
    nbt = _load_nbt(p)
    palette = {int(v): str(k) for k, v in nbt["Palette"].items()}
    indices = _decode_varints(bytes(nbt["BlockData"]))
    block_count = sum(
        1 for i in indices if not _is_air(palette.get(i, "minecraft:air"))
    )
    return {
        "path": str(p),
        "file_size_kb": round(p.stat().st_size / 1024, 1),
        "width": width,
        "height": height,
        "length": length,
        "block_count": block_count,
        "palette_size": len(palette),
        "top_blocks": top,
        "mtime": os.path.getmtime(p),
    }


def schem_size_mismatch(
    summary: Dict[str, Any],
    zone_width: int,
    zone_depth: int,
    *,
    tolerance: float = 1.5,
) -> Optional[str]:
    """schem 外接サイズがゾーンより大きすぎる場合に警告文を返す。"""
    target = max(int(zone_width), int(zone_depth))
    sw = int(summary.get("width", 0))
    sl = int(summary.get("length", 0))
    longest = max(sw, sl)
    if target <= 0 or longest <= 0:
        return None
    if longest > target * tolerance:
        return (
            f"schem の最長辺 **{longest}** ブロックに対し、"
            f"ゾーン最長辺は **{target}** ブロックです（{longest / target:.1f} 倍）。"
            " Tripo の mesh→stylize 経路ではサイズがずれやすい既知課題です。"
            " 詳細: docs/KNOWN_CHALLENGES.md §1"
        )
    return None
