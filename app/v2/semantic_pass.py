"""
Gemini 3 Pro Vision: ボクセル座標系と一致する窓・ドア・装飾の setblock 上書きを JSON で生成する。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    from ai.providers.stage_client import complete_json
    from ai.routing import AIStage
except ImportError:
    from app.ai.providers.stage_client import complete_json
    from app.ai.routing import AIStage


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


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0]
    return t.strip()


def run_semantic_pass(
    image_path: str,
    blocks: List[Dict[str, Any]],
    building_info: Dict[str, Any],
    *,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    戻り値例:
    {
      "windows": [...],
      "doors": [...],
      "block_overrides": [{"x","y","z","block":"minecraft:..."}, ...]
    }
    """
    if not blocks:
        return {"windows": [], "doors": [], "block_overrides": []}

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    ext = os.path.splitext(image_path)[1].lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(
        ext, "image/jpeg"
    )

    bbox = _bbox(blocks)
    name = building_info.get("name", "")
    desc = building_info.get("description", "")
    facing = building_info.get("facing", "south")

    system = """You are a Minecraft build semantic analyst.
The image shows the target building. A voxel reconstruction already exists in integer grid coordinates.
Your job: propose SMALL sets of precise changes — windows, doors, lanterns, fence, banners — aligned with the image.

OUTPUT: Valid JSON only (no markdown) with this shape:
{
  "windows": [
    {"x": int, "y": int, "z": int, "width": int, "height": int, "facing": "north"|"south"|"east"|"west"}
  ],
  "doors": [
    {"x": int, "y": int, "z": int, "facing": "north"|"south"|"east"|"west", "is_double": bool, "door_type": "oak_door"|"dark_oak_door"|"spruce_door"|"birch_door"|"iron_door"}
  ],
  "block_overrides": [
    {"x": int, "y": int, "z": int, "block": "minecraft:block_id[state_if_needed]"}
  ]
}

Rules:
- All coordinates MUST lie inside the bounding box given in the user message (inclusive).
- Use minecraft: namespace for every block id in block_overrides.
- For glass panes use e.g. minecraft:glass_pane[facing=south,waterlogged=false] with correct facing.
- For doors you may include two block_overrides (lower and upper halves) OR leave doors only in "doors" — both are ok.
- Keep total block_overrides + explicit window+door slots reasonable (under 200 entries) — only visible features from the image.
- If unsure about a feature, omit it rather than guess random coordinates.
"""

    user = f"""Building name: {name}
Description: {desc}
Preferred facade / entrance facing: {facing}

Voxel bounding box (integer inclusive):
{json.dumps(bbox, ensure_ascii=False)}

Voxel count: {len(blocks)}

Return JSON as specified."""

    raw = complete_json(
        AIStage.SEMANTIC_PASS,
        system=system,
        user=user,
        temperature=temperature,
        image_bytes=image_bytes,
        image_mime=mime,
    )
    try:
        data = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError:
        return {"windows": [], "doors": [], "block_overrides": [], "raw_error": raw[:2000]}

    data.setdefault("windows", [])
    data.setdefault("doors", [])
    data.setdefault("block_overrides", [])
    return data


def clamp_semantic_to_bbox(data: Dict[str, Any], bbox: Dict[str, int]) -> Dict[str, Any]:
    """BBox 外の座標を削除（軽いガード）。"""

    def _in_box(x: int, y: int, z: int) -> bool:
        return (
            bbox["min_x"] <= x <= bbox["max_x"]
            and bbox["min_y"] <= y <= bbox["max_y"]
            and bbox["min_z"] <= z <= bbox["max_z"]
        )

    out = {"windows": [], "doors": [], "block_overrides": []}
    for w in data.get("windows") or []:
        try:
            if _in_box(int(w["x"]), int(w["y"]), int(w["z"])):
                out["windows"].append(w)
        except (KeyError, TypeError, ValueError):
            continue
    for d in data.get("doors") or []:
        try:
            if _in_box(int(d["x"]), int(d["y"]), int(d["z"])):
                out["doors"].append(d)
        except (KeyError, TypeError, ValueError):
            continue
    for o in data.get("block_overrides") or []:
        try:
            if _in_box(int(o["x"]), int(o["y"]), int(o["z"])):
                blk = str(o.get("block", "")).strip()
                if blk and re.match(r"minecraft:[a-z0-9_]+", blk.split("[", 1)[0]):
                    out["block_overrides"].append(
                        {"x": int(o["x"]), "y": int(o["y"]), "z": int(o["z"]), "block": blk}
                    )
        except (KeyError, TypeError, ValueError):
            continue
    return out
