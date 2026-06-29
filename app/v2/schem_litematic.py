"""``.schem`` → ``.litematic`` 変換（オプション・litemapy 依存）。"""
from __future__ import annotations

from pathlib import Path

from v2.schem_preview import SchemPreviewError, parse_schem_blocks


def export_litematic_from_schem(schem_path: str | Path, litematic_path: str | Path) -> Path:
    """Sponge schem を litematic に書き出す。要 ``pip install litemapy``。"""
    try:
        from litemapy import BlockState, Region, Schematic
    except ImportError as e:
        raise SchemPreviewError(
            "`.litematic` 書き出しには litemapy が必要です: `pip install litemapy`"
        ) from e

    blocks = parse_schem_blocks(schem_path, skip_air=True)
    if not blocks:
        raise SchemPreviewError("書き出すブロックがありません")

    max_x = max(int(b["x"]) for b in blocks)
    max_y = max(int(b["y"]) for b in blocks)
    max_z = max(int(b["z"]) for b in blocks)
    w, h, l = max_x + 1, max_y + 1, max_z + 1

    region = Region(0, 0, 0, w, h, l)
    for b in blocks:
        bid = str(b["type"])
        name = bid.split("[", 1)[0]
        props: dict = {}
        if "[" in bid:
            inner = bid.split("[", 1)[1].rstrip("]")
            for part in inner.split(","):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    props[k.strip()] = v.strip()
        region[int(b["x"]), int(b["y"]), int(b["z"])] = BlockState(name, props)

    schem = Schematic()
    schem.regions["Bananacraft"] = region
    out = Path(litematic_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    schem.save(str(out))
    return out


__all__ = ["export_litematic_from_schem"]
