"""3D Preview module for Bananacraft 2.0

Plotly Mesh3d でブロックを実際の立方体として描画する。

特徴:
- 各ブロックを 8 頂点 / 12 三角形の立方体メッシュで表現。
- 隣接ブロックがあるフェイスは描画しない (隠面除去) → 頂点数と陰影性を両立。
- 同色のブロックを 1 trace にまとめてブラウザ負荷を抑制。
- フェイス向きで簡易シェーディング (上面 1.0 / 横面 0.8 / 下面 0.55) → Minecraft 風の陰影。
- isometric カメラ (orthographic) で見やすい建築物プレビュー。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go


# ----- Block color atlas -----------------------------------------------
BLOCK_COLORS: Dict[str, str] = {
    # Stone variants
    "stone": "#7F7F7F",
    "stone_bricks": "#7A7A7A",
    "cobblestone": "#6B6B6B",
    "andesite": "#8A8A8A",
    "diorite": "#C8C8C8",
    "granite": "#9B6B5B",
    "brick": "#8B4513",
    "bricks": "#8B4513",
    "nether_brick": "#2B1414",
    "deepslate": "#4A4A4A",
    "mossy_cobblestone": "#5F6B4E",

    # Glass / windows
    "glass": "#ADD8E6",
    "glass_pane": "#ADD8E6",
    "white_stained_glass": "#FFFFFF",
    "light_blue_stained_glass": "#87CEEB",
    "yellow_stained_glass": "#F2D44A",

    # Wood
    "oak_planks": "#B8945F",
    "oak_log": "#6B5038",
    "spruce_planks": "#5E4A32",
    "spruce_log": "#3B2816",
    "birch_planks": "#D5C98C",
    "birch_log": "#E2D9B4",
    "jungle_planks": "#B07E5A",
    "dark_oak_planks": "#3E2912",
    "acacia_planks": "#B26A33",

    # Metals
    "iron_block": "#D8D8D8",
    "gold_block": "#FFDF00",
    "copper_block": "#C17952",
    "diamond_block": "#5CD2D5",
    "emerald_block": "#37D161",
    "lapis_block": "#1E429F",

    # Natural
    "grass_block": "#7CBA4E",
    "dirt": "#8B6914",
    "sand": "#DBCFA0",
    "sandstone": "#D9C97C",
    "red_sand": "#BF7847",
    "red_sandstone": "#BA6A39",
    "netherrack": "#6F2D2D",
    "obsidian": "#1A0F2C",

    # Honey / bee
    "honey_block": "#F4A100",
    "honeycomb_block": "#E4922B",
    "bee_nest": "#C9824A",
    "beehive": "#D8A055",

    # Decorative
    "quartz_block": "#EBE8E4",
    "smooth_quartz": "#EBE8E4",
    "prismarine": "#639D94",
    "sea_lantern": "#9BEBE8",
    "glowstone": "#FFE87C",
    "snow_block": "#FAFAFA",
    "bone_block": "#E1DBB8",
    "terracotta": "#985E43",

    # Colored blocks (concrete)
    "white_concrete": "#CFD5D6",
    "orange_concrete": "#E06401",
    "magenta_concrete": "#A9309F",
    "light_blue_concrete": "#36689D",
    "yellow_concrete": "#F0AF15",
    "lime_concrete": "#5EA919",
    "pink_concrete": "#D5658F",
    "gray_concrete": "#36393D",
    "light_gray_concrete": "#7D7D73",
    "cyan_concrete": "#157788",
    "purple_concrete": "#641F9C",
    "blue_concrete": "#2C2E8F",
    "brown_concrete": "#603C20",
    "green_concrete": "#495B24",
    "red_concrete": "#8E2121",
    "black_concrete": "#080A0F",

    # Colored blocks (terracotta)
    "white_terracotta": "#D1B1A1",
    "orange_terracotta": "#A0541D",
    "magenta_terracotta": "#95576C",
    "light_blue_terracotta": "#716C8A",
    "yellow_terracotta": "#BA8523",
    "lime_terracotta": "#677535",
    "pink_terracotta": "#A24E4F",
    "gray_terracotta": "#3A2C28",
    "light_gray_terracotta": "#876B62",
    "cyan_terracotta": "#565B5B",
    "purple_terracotta": "#76443A",
    "blue_terracotta": "#4A3B5B",
    "brown_terracotta": "#4D3324",
    "green_terracotta": "#4C532A",
    "red_terracotta": "#8E3D2E",
    "black_terracotta": "#251610",

    "default": "#808080",
}


def get_block_color(block_type: str) -> str:
    """ブロック ID -> 16 進カラーコード."""
    if block_type.startswith("minecraft:"):
        block_type = block_type[10:]
    if "[" in block_type:
        block_type = block_type.split("[")[0]

    for suffix in ("_slab", "_stairs", "_wall", "_fence"):
        if block_type.endswith(suffix):
            base = block_type[: -len(suffix)]
            if base in BLOCK_COLORS:
                return BLOCK_COLORS[base]

    if block_type in BLOCK_COLORS:
        return BLOCK_COLORS[block_type]

    # 緩めの部分一致 (e.g. "stone_brick_stairs" → "stone_bricks")
    for key, color in BLOCK_COLORS.items():
        if key in block_type or block_type in key:
            return color

    return BLOCK_COLORS["default"]


# ----- Color helpers ---------------------------------------------------

def _hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _shade_hex(c: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(c)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02X}{g:02X}{b:02X}"


# ----- Cube geometry ---------------------------------------------------

# 立方体 (x, y, z) -> (x+1, y+1, z+1) の 8 頂点
_CUBE_VERTS = np.array(
    [
        (0, 0, 0),  # 0
        (1, 0, 0),  # 1
        (1, 1, 0),  # 2
        (0, 1, 0),  # 3
        (0, 0, 1),  # 4
        (1, 0, 1),  # 5
        (1, 1, 1),  # 6
        (0, 1, 1),  # 7
    ],
    dtype=np.float32,
)

# 各フェイス: (i, j, k, neighbor_offset, shade_factor)
# Plotly の Mesh3d は三角形なので 1 フェイス = 2 三角形 (i, j, k リストに追加)
# neighbor_offset は「このフェイスを塞ぐ隣接ブロックのオフセット」
_FACES: List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int], float]] = [
    # (頂点 4 つ, 隣接オフセット, シェーディング係数)
    # 上面 (y+) — 一番明るい
    ((3, 2, 6, 7), (0, 1, 0), 1.00),
    # 下面 (y-) — 一番暗い
    ((0, 1, 5, 4), (0, -1, 0), 0.55),
    # 北 (z-)
    ((0, 1, 2, 3), (0, 0, -1), 0.78),
    # 南 (z+)
    ((4, 5, 6, 7), (0, 0, 1), 0.85),
    # 東 (x+)
    ((1, 2, 6, 5), (1, 0, 0), 0.82),
    # 西 (x-)
    ((0, 3, 7, 4), (-1, 0, 0), 0.72),
]


def _strip_state(block_type: str) -> str:
    if "[" in block_type:
        block_type = block_type.split("[")[0]
    return block_type


def _build_traces(blocks: List[Dict]) -> List[go.Mesh3d]:
    """ブロックリストを Mesh3d trace のリストに変換 (色ごとに集約)."""
    if not blocks:
        return []

    # 1. ブロックの存在を高速判定するための set
    positions: set[Tuple[int, int, int]] = set()
    for b in blocks:
        positions.add((int(b["x"]), int(b["y"]), int(b["z"])))

    # 2. 色 (シェーディング後) でフェイス頂点をバケット化
    #    key: shaded hex color -> {"x": [...], "y": [...], "z": [...], "i": [...], "j": [...], "k": [...], "hover": [...]}
    buckets: Dict[str, Dict[str, List]] = {}

    for b in blocks:
        bx, by, bz = int(b["x"]), int(b["y"]), int(b["z"])
        block_type = b.get("type", "stone")
        base_color = get_block_color(block_type)
        clean_type = _strip_state(block_type).replace("minecraft:", "")
        hover_label = f"{clean_type} ({bx}, {by}, {bz})"

        for verts, neighbor, shade in _FACES:
            nx, ny, nz = neighbor
            if (bx + nx, by + ny, bz + nz) in positions:
                continue  # 隠面: 描画しない

            shaded = _shade_hex(base_color, shade)
            bucket = buckets.setdefault(
                shaded,
                {"x": [], "y": [], "z": [], "i": [], "j": [], "k": [], "hover": []},
            )

            base_idx = len(bucket["x"])
            for vidx in verts:
                vx, vy, vz = _CUBE_VERTS[vidx]
                bucket["x"].append(bx + float(vx))
                bucket["y"].append(by + float(vy))
                bucket["z"].append(bz + float(vz))
                bucket["hover"].append(hover_label)

            # 四角形を 2 つの三角形に: (0,1,2) と (0,2,3)
            bucket["i"].extend([base_idx + 0, base_idx + 0])
            bucket["j"].extend([base_idx + 1, base_idx + 2])
            bucket["k"].extend([base_idx + 2, base_idx + 3])

    traces: List[go.Mesh3d] = []
    for color, data in buckets.items():
        if not data["i"]:
            continue
        # Minecraft 座標系で表示: 内部 (x, y(=up), z) を Plotly の (x, z, y) にスワップ
        traces.append(
            go.Mesh3d(
                x=data["x"],
                y=data["z"],
                z=data["y"],
                i=data["i"],
                j=data["j"],
                k=data["k"],
                color=color,
                flatshading=True,
                lighting=dict(ambient=0.85, diffuse=0.25, specular=0.0, roughness=1.0),
                hoverinfo="text",
                text=data["hover"],
                showscale=False,
                name=color,
            )
        )

    return traces


def _empty_figure(message: str = "No blocks to display") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
    )
    return fig


def create_3d_preview(blocks: List[Dict], title: str = "Building Preview") -> go.Figure:
    """ブロック群を Mesh3d で描画する Minecraft 風 3D プレビュー."""
    if not blocks:
        return _empty_figure()

    traces = _build_traces(blocks)
    if not traces:
        return _empty_figure()

    fig = go.Figure(data=traces)

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#FFE3A8")),
        scene=dict(
            xaxis=dict(
                title="X",
                showgrid=False,
                zeroline=False,
                showbackground=False,
                color="#8B7355",
            ),
            yaxis=dict(
                title="Z",
                showgrid=False,
                zeroline=False,
                showbackground=False,
                color="#8B7355",
            ),
            zaxis=dict(
                title="Y (Height)",
                showgrid=False,
                zeroline=False,
                showbackground=False,
                color="#8B7355",
            ),
            aspectmode="data",
            camera=dict(
                projection=dict(type="orthographic"),
                eye=dict(x=1.6, y=1.6, z=1.0),
                up=dict(x=0, y=0, z=1),
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=40, b=0),
        height=600,
        showlegend=False,
    )

    return fig


def create_3d_preview_colored_by_type(
    blocks: List[Dict], title: str = "Building Preview"
) -> go.Figure:
    """互換 API: 凡例を出したい場合に使うが、現状は create_3d_preview を呼ぶ."""
    return create_3d_preview(blocks, title=title)


def get_block_statistics(blocks: List[Dict]) -> Dict[str, Any]:
    """ブロック配置の統計情報を返す."""
    if not blocks:
        return {"total": 0}

    type_counts: Dict[str, int] = {}
    for block in blocks:
        block_type = block.get("type", "unknown").replace("minecraft:", "")
        if "[" in block_type:
            block_type = block_type.split("[")[0]
        type_counts[block_type] = type_counts.get(block_type, 0) + 1

    x_coords = [b["x"] for b in blocks]
    y_coords = [b["y"] for b in blocks]
    z_coords = [b["z"] for b in blocks]

    return {
        "total": len(blocks),
        "type_distribution": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "bounding_box": {
            "x": (min(x_coords), max(x_coords)),
            "y": (min(y_coords), max(y_coords)),
            "z": (min(z_coords), max(z_coords)),
        },
        "dimensions": {
            "width": max(x_coords) - min(x_coords) + 1,
            "height": max(y_coords) - min(y_coords) + 1,
            "depth": max(z_coords) - min(z_coords) + 1,
        },
    }
