"""
Mesh 由来のブロック集合から、旧 Architect / BlueprintAnalyzer 互換の最小 instructions を合成する。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


def _strip_mc(name: str) -> str:
    name = (name or "").strip()
    if name.startswith("minecraft:"):
        return name[len("minecraft:") :].split("[", 1)[0]
    return name.split("[", 1)[0]


def _dominant_material(blocks: List[Dict[str, Any]], pred) -> str:
    c: Counter[str] = Counter()
    for b in blocks:
        if pred(b):
            c[_strip_mc(b.get("type", "stone_bricks"))] += 1
    if not c:
        return "stone_bricks"
    return c.most_common(1)[0][0]


def _bbox(blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    xs = [int(b["x"]) for b in blocks]
    ys = [int(b["y"]) for b in blocks]
    zs = [int(b["z"]) for b in blocks]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "min_z": min(zs),
        "max_z": max(zs),
    }


def build_minimal_instructions(
    blocks: List[Dict[str, Any]],
    building_info: Dict[str, Any],
    semantic: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    draw_plane（床・外周4壁・上蓋）+ semantic の place_window / place_door を並べる。
    """
    if not blocks:
        return []

    bb = _bbox(blocks)
    mx0, mx1 = bb["min_x"], bb["max_x"]
    my0, my1 = bb["min_y"], bb["max_y"]
    mz0, mz1 = bb["min_z"], bb["max_z"]

    floor_m = _dominant_material(
        blocks, lambda b: int(b["y"]) == my0 and mx0 <= int(b["x"]) <= mx1 and mz0 <= int(b["z"]) <= mz1
    )
    if floor_m == "air":
        floor_m = "stone_bricks"

    wall_mx0 = _dominant_material(blocks, lambda b: int(b["x"]) == mx0)
    wall_mx1 = _dominant_material(blocks, lambda b: int(b["x"]) == mx1)
    wall_mz0 = _dominant_material(blocks, lambda b: int(b["z"]) == mz0)
    wall_mz1 = _dominant_material(blocks, lambda b: int(b["z"]) == mz1)
    roof_m = _dominant_material(blocks, lambda b: int(b["y"]) == my1)

    facing_default = (building_info.get("facing") or "south").lower()
    if facing_default not in ("north", "south", "east", "west"):
        facing_default = "south"

    instructions: List[Dict[str, Any]] = []

    def _inst(tool: str, params: dict, reasoning: str = "") -> Dict[str, Any]:
        return {"tool_name": tool, "parameters": params, "reasoning": reasoning or None}

    # Floor
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx0, my0, mz0], [mx1, my0, mz0]],
                "edge_b": [[mx0, my0, mz1], [mx1, my0, mz1]],
                "material": floor_m,
            },
            "floor",
        )
    )
    # Walls (outer shell guides for BlueprintAnalyzer)
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx0, my0, mz0], [mx0, my0, mz1]],
                "edge_b": [[mx0, my1, mz0], [mx0, my1, mz1]],
                "material": wall_mx0,
            },
            "wall -X",
        )
    )
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx1, my0, mz0], [mx1, my0, mz1]],
                "edge_b": [[mx1, my1, mz0], [mx1, my1, mz1]],
                "material": wall_mx1,
            },
            "wall +X",
        )
    )
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx0, my0, mz0], [mx1, my0, mz0]],
                "edge_b": [[mx0, my1, mz0], [mx1, my1, mz0]],
                "material": wall_mz0,
            },
            "wall -Z",
        )
    )
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx0, my0, mz1], [mx1, my0, mz1]],
                "edge_b": [[mx0, my1, mz1], [mx1, my1, mz1]],
                "material": wall_mz1,
            },
            "wall +Z",
        )
    )
    # Roof cap (flat bbox cover — mesh detail is already in voxels)
    instructions.append(
        _inst(
            "draw_plane",
            {
                "edge_a": [[mx0, my1, mz0], [mx1, my1, mz0]],
                "edge_b": [[mx0, my1, mz1], [mx1, my1, mz1]],
                "material": roof_m if roof_m != "air" else "stone_bricks",
            },
            "roof",
        )
    )

    sem = semantic or {}
    for w in sem.get("windows") or []:
        try:
            instructions.append(
                _inst(
                    "place_window",
                    {
                        "position": [int(w["x"]), int(w["y"]), int(w["z"])],
                        "width": int(w.get("width", 2)),
                        "height": int(w.get("height", 2)),
                        "facing": str(w.get("facing", facing_default)),
                        "glass_type": "glass_pane",
                        "frame_material": "oak_planks",
                        "has_flower_box": False,
                    },
                    "semantic window",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    for d in sem.get("doors") or []:
        try:
            instructions.append(
                _inst(
                    "place_door",
                    {
                        "position": [int(d["x"]), int(d["y"]), int(d["z"])],
                        "facing": str(d.get("facing", facing_default)),
                        "door_type": str(d.get("door_type", "oak_door")),
                        "is_double": bool(d.get("is_double", False)),
                        "has_porch": False,
                    },
                    "semantic door",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    return instructions
