"""コンセプト・建物情報から、出来高に使う Minecraft ブロックパレットを推定する。

優先度:
1. キーワードフォールバック (オフライン辞書)  ← 必ず動く下地
2. Gemini が利用可能なら、辞書の結果を補完するように JSON 配列で 12-16 個提案させる

最終的に返るのは `BlockAssigner.DEFAULT_PALETTE` に存在する `minecraft:...` ID のみ。
パイプラインを止めない: 例外時はキーワード結果 (空でも) を返す。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

try:
    from voxelizer.block_assigner import BlockAssigner
except ImportError:
    from app.voxelizer.block_assigner import BlockAssigner

try:
    from ai.providers.stage_client import complete_json
    from ai.routing import AIStage
except ImportError:
    from app.ai.providers.stage_client import complete_json
    from app.ai.routing import AIStage


# ---- キーワード -> パレット辞書 -----------------------------------------
# 同じパレットでも順番が重要。前にある方が「主役」として認識される。
# DEFAULT_PALETTE 内に存在する ID のみ並べる。
_HONEY = [
    "minecraft:honey_block",
    "minecraft:honeycomb_block",
    "minecraft:yellow_terracotta",
    "minecraft:yellow_concrete",
    "minecraft:oak_log",
    "minecraft:oak_planks",
    "minecraft:spruce_planks",
    "minecraft:dark_oak_planks",
    "minecraft:gold_block",
    "minecraft:sandstone",
]
_WOOD = [
    "minecraft:oak_log",
    "minecraft:oak_planks",
    "minecraft:spruce_planks",
    "minecraft:birch_planks",
    "minecraft:dark_oak_planks",
    "minecraft:jungle_planks",
    "minecraft:brown_terracotta",
    "minecraft:bricks",
    "minecraft:cobblestone",
    "minecraft:stone",
]
_STONE_CASTLE = [
    "minecraft:stone",
    "minecraft:cobblestone",
    "minecraft:andesite",
    "minecraft:diorite",
    "minecraft:granite",
    "minecraft:deepslate",
    "minecraft:oak_planks",
    "minecraft:spruce_planks",
    "minecraft:bricks",
    "minecraft:iron_block",
    "minecraft:gray_concrete",
    "minecraft:gray_terracotta",
]
_DESERT = [
    "minecraft:sandstone",
    "minecraft:sand",
    "minecraft:red_sandstone",
    "minecraft:red_sand",
    "minecraft:terracotta",
    "minecraft:orange_terracotta",
    "minecraft:yellow_terracotta",
    "minecraft:brown_terracotta",
    "minecraft:white_terracotta",
    "minecraft:bricks",
]
_NETHER_FIRE = [
    "minecraft:netherrack",
    "minecraft:red_concrete",
    "minecraft:red_terracotta",
    "minecraft:black_concrete",
    "minecraft:black_terracotta",
    "minecraft:obsidian",
    "minecraft:deepslate",
    "minecraft:gold_block",
]
_ICE_SNOW = [
    "minecraft:snow_block",
    "minecraft:white_concrete",
    "minecraft:light_blue_concrete",
    "minecraft:cyan_concrete",
    "minecraft:white_terracotta",
    "minecraft:diamond_block",
    "minecraft:quartz_block",
    "minecraft:spruce_planks",
    "minecraft:stone",
]
_FOREST_NATURE = [
    "minecraft:oak_log",
    "minecraft:oak_planks",
    "minecraft:spruce_log",  # フォールバック; 不在なら filter で消える
    "minecraft:spruce_planks",
    "minecraft:birch_planks",
    "minecraft:green_concrete",
    "minecraft:green_terracotta",
    "minecraft:lime_terracotta",
    "minecraft:cobblestone",
    "minecraft:mossy_cobblestone",  # 不在なら除外
    "minecraft:bricks",
]
_OCEAN_AQUA = [
    "minecraft:prismarine",
    "minecraft:blue_concrete",
    "minecraft:cyan_concrete",
    "minecraft:light_blue_concrete",
    "minecraft:blue_terracotta",
    "minecraft:cyan_terracotta",
    "minecraft:quartz_block",
    "minecraft:sandstone",
]
_PURPLE_MAGIC = [
    "minecraft:purple_concrete",
    "minecraft:magenta_concrete",
    "minecraft:purple_terracotta",
    "minecraft:magenta_terracotta",
    "minecraft:obsidian",
    "minecraft:deepslate",
    "minecraft:gold_block",
    "minecraft:emerald_block",
    "minecraft:dark_oak_planks",
]

# 汎用デフォルト: 何のキーワードにも当たらない場合の無難なセット (中世風)
_GENERIC_DEFAULT = [
    "minecraft:oak_planks",
    "minecraft:spruce_planks",
    "minecraft:dark_oak_planks",
    "minecraft:cobblestone",
    "minecraft:stone",
    "minecraft:bricks",
    "minecraft:sandstone",
    "minecraft:gray_concrete",
    "minecraft:white_terracotta",
    "minecraft:brown_terracotta",
]

# (lower-case パターン -> パレット候補) を順に確認し、合致したものをマージ
_KEYWORD_RULES: List[tuple[List[str], List[str]]] = [
    (["honey", "hone", "ハチミツ", "蜂蜜", "蜜", "bee", "蜂", "ミツバチ", "蜂の巣"], _HONEY),
    (["nether", "fire", "炎", "溶岩", "lava", "地獄", "悪魔"], _NETHER_FIRE),
    (["snow", "ice", "雪", "氷", "frozen", "frost", "winter", "北極", "極地"], _ICE_SNOW),
    (["desert", "砂漠", "sand", "サハラ", "オアシス", "ピラミッド", "pyramid"], _DESERT),
    (["ocean", "sea", "海", "underwater", "海底", "aqua", "プール"], _OCEAN_AQUA),
    (["magic", "魔法", "魔術", "魔女", "wizard", "mage", "wizardry", "purple", "紫"], _PURPLE_MAGIC),
    (["castle", "城", "fortress", "要塞", "stone", "石造", "石"], _STONE_CASTLE),
    (["forest", "森", "tree", "ジャングル", "jungle", "nature", "自然", "村", "village"], _FOREST_NATURE),
    (["wood", "木", "木造", "log", "plank", "木材", "small house", "cabin", "ログハウス"], _WOOD),
]


def _allowed_block_set() -> set[str]:
    """DEFAULT_PALETTE 内に存在するブロック ID 集合（atlas 不在ブロックも事前に許容しておく）。"""
    return set(BlockAssigner.DEFAULT_PALETTE)


def _filter_to_allowed(ids: List[str], allowed: set[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for b in ids:
        if not isinstance(b, str):
            continue
        b = b.strip()
        if not b:
            continue
        if not b.startswith("minecraft:"):
            b = f"minecraft:{b}"
        if b in allowed and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _keyword_palette(concept_text: str, building_info: Dict[str, Any]) -> List[str]:
    haystack = " ".join(
        str(x or "") for x in (
            concept_text,
            building_info.get("name", ""),
            building_info.get("description", ""),
            building_info.get("type", ""),
        )
    ).lower()

    merged: List[str] = []
    for patterns, palette in _KEYWORD_RULES:
        if any(p.lower() in haystack for p in patterns):
            for b in palette:
                if b not in merged:
                    merged.append(b)

    if not merged:
        merged = list(_GENERIC_DEFAULT)

    return merged


def _gemini_palette(
    concept_text: str, building_info: Dict[str, Any], allowed: set[str]
) -> List[str]:
    """Gemini に問い合わせて 12-16 個提案。失敗時は空リストを返す。"""
    name = building_info.get("name", "")
    desc = building_info.get("description", "")
    btype = building_info.get("type", "")

    allowed_sorted = sorted(allowed)
    system = (
        "You are a Minecraft palette curator. "
        "Given a building concept, return between 12 and 16 Minecraft block IDs "
        "(namespaced like 'minecraft:oak_planks') that best match the visual world "
        "for that building. Only pick IDs from the allowed list. Output a JSON "
        "object with a single field 'palette' that is a JSON array of strings, "
        "ordered from most prominent to least."
    )
    user = (
        f"Concept context:\n{concept_text}\n\n"
        f"Building: name={name!r} type={btype!r}\nDescription: {desc}\n\n"
        f"Allowed block IDs (pick 12-16 from here):\n{json.dumps(allowed_sorted)}"
    )

    try:
        raw = complete_json(
            AIStage.SEMANTIC_PASS,
            system=system,
            user=user,
            temperature=0.4,
        )
    except Exception:
        return []

    if not raw:
        return []

    text = raw.strip()
    # JSON フェンスを除去
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]

    try:
        data = json.loads(text)
    except Exception:
        # 最後の手段: 配列だけを抜き出してみる
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []

    if isinstance(data, dict):
        ids = data.get("palette") or data.get("blocks") or data.get("ids")
    elif isinstance(data, list):
        ids = data
    else:
        ids = []

    return _filter_to_allowed(list(ids or []), allowed)


def infer_palette(
    concept_text: str,
    building_info: Dict[str, Any],
    *,
    use_gemini: Optional[bool] = None,
    min_size: int = 8,
    max_size: int = 16,
) -> List[str]:
    """テーマパレットを推定する。

    Args:
        concept_text: コンセプトの説明文（自然言語）。
        building_info: `name`, `description`, `type` を含む dict。
        use_gemini: None なら自動判定（環境キーが設定済みかで判定）。
        min_size / max_size: 返すパレットの上下限。

    Returns:
        `minecraft:...` ID の list。空にはならない (フォールバックあり)。
    """
    allowed = _allowed_block_set()

    base = _filter_to_allowed(_keyword_palette(concept_text, building_info), allowed)

    if not base:
        base = _filter_to_allowed(_GENERIC_DEFAULT, allowed)

    should_try_gemini = use_gemini if use_gemini is not None else True

    if should_try_gemini:
        gem = _gemini_palette(concept_text, building_info, allowed)
        if gem:
            # Gemini を主役、キーワード由来を補欠として追加（重複は除外）
            seen = set(gem)
            for b in base:
                if b not in seen:
                    seen.add(b)
                    gem.append(b)
            base = gem

    # 上下限を調整
    if len(base) < min_size:
        for b in _filter_to_allowed(_GENERIC_DEFAULT, allowed):
            if b not in base:
                base.append(b)
            if len(base) >= min_size:
                break
    if len(base) > max_size:
        base = base[:max_size]

    return base
