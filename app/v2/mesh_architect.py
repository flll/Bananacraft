"""
Mesh-First Architect: Tripo3D → GLB → ボクセル化 → BlockAssign → Gemini セマンティクス上書き。
"""
from __future__ import annotations

import glob
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

ProgressCallback = Callable[[str, Optional[str]], None]
"""進捗報告コールバック。(label, detail) を受け取る。"""

try:
    from file_manager import FileManager
    from tripo_client import TripoClient
    from voxelizer.mesh_loader import load_mesh
    from voxelizer.bvh_ray_voxelizer import voxelize_mesh
    from voxelizer.block_assigner import BlockAssigner
    from v2.semantic_pass import run_semantic_pass, clamp_semantic_to_bbox
    from v2.instructions_synthesizer import build_minimal_instructions
except ImportError:
    from app.file_manager import FileManager
    from app.tripo_client import TripoClient
    from app.voxelizer.mesh_loader import load_mesh
    from app.voxelizer.bvh_ray_voxelizer import voxelize_mesh
    from app.voxelizer.block_assigner import BlockAssigner
    from app.v2.semantic_pass import run_semantic_pass, clamp_semantic_to_bbox
    from app.v2.instructions_synthesizer import build_minimal_instructions


def _assigned_to_blocks(assigned) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ab in assigned:
        x, y, z = ab.position
        out.append({"x": int(x), "y": int(y), "z": int(z), "type": ab.get_full_block_id()})
    return out


def _normalize_ground(blocks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    if not blocks:
        return [], 0
    min_y = min(int(b["y"]) for b in blocks)
    for b in blocks:
        b["y"] = int(b["y"]) - min_y
    return blocks, min_y


def _strip_block_state(block_id: str) -> str:
    """`minecraft:oak_log[axis=y]` -> `minecraft:oak_log` 形式に正規化."""
    if "[" in block_id:
        return block_id.split("[", 1)[0]
    return block_id


# パレットに無くても許容する「機能ブロック」: 窓・ドア・照明など。
# これらは semantic_pass の意図を尊重して残す（テーマ整合性より機能性を優先）。
_SEMANTIC_FUNCTIONAL_KEYWORDS = (
    "glass",
    "door",
    "lantern",
    "torch",
    "trapdoor",
    "fence",
    "fence_gate",
    "stairs",
    "slab",
    "wall",
    "carpet",
    "banner",
    "campfire",
    "candle",
    "barrel",
    "bookshelf",
    "ladder",
    "leaves",
    "bee_nest",
    "beehive",
    "flower",
    "sapling",
    "redstone",
    "rail",
)


def _is_functional(block_id: str) -> bool:
    bare = _strip_block_state(block_id)
    name = bare.split(":", 1)[-1]
    return any(kw in name for kw in _SEMANTIC_FUNCTIONAL_KEYWORDS)


def _merge_block_overrides(
    blocks: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
    palette: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """semantic_pass の overrides を反映する。

    `palette` が指定された場合、パレット外かつ機能ブロックでもないブロックは
    テーマ整合性のためスキップする。窓・ドア・照明などは常に許可。
    """
    allowed: Optional[set[str]] = None
    if palette:
        allowed = {_strip_block_state(b) for b in palette}

    idx: Dict[Tuple[int, int, int], int] = {}
    for i, b in enumerate(blocks):
        idx[(int(b["x"]), int(b["y"]), int(b["z"]))] = i

    for o in overrides:
        k = (int(o["x"]), int(o["y"]), int(o["z"]))
        blk = str(o["block"])
        if allowed is not None:
            bare = _strip_block_state(blk)
            if bare not in allowed and not _is_functional(blk):
                continue
        if k in idx:
            blocks[idx[k]]["type"] = blk
        else:
            blocks.append({"x": k[0], "y": k[1], "z": k[2], "type": blk})
    return blocks


def _mesh_cache_paths(project_dir: str, zone_id: Any) -> List[str]:
    pattern = os.path.join(project_dir, f"mesh_{zone_id}.*")
    return sorted(p for p in glob.glob(pattern) if os.path.isfile(p))


def _pick_mesh_cache(paths: List[str]) -> Optional[str]:
    if not paths:
        return None
    order = {".glb": 0, ".gltf": 1, ".obj": 2, ".fbx": 3, ".stl": 4, ".ply": 5}

    def sort_key(p: str) -> Tuple[int, float]:
        ext = os.path.splitext(p)[1].lower()
        return order.get(ext, 99), -os.path.getmtime(p)

    return sorted(paths, key=sort_key)[0]


def _clear_mesh_cache(fm: FileManager, zone_id: Any) -> None:
    for p in _mesh_cache_paths(fm.project_dir, zone_id):
        try:
            os.remove(p)
        except OSError:
            pass
    task_json = fm.get_path(f"tripo_task_{zone_id}.json")
    if os.path.isfile(task_json):
        try:
            os.remove(task_json)
        except OSError:
            pass


def _bbox_dict(blocks: List[Dict[str, Any]]) -> Dict[str, int]:
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


class MeshArchitect:
    """旧 Architect と入れ替え用。UI から 1 ボタンで blocks + instructions を生成する。"""

    def __init__(self, fm: FileManager):
        self.fm = fm

    def build_from_image(
        self,
        image_path: str,
        building_info: Dict[str, Any],
        *,
        force: bool = False,
        skip_semantic: bool = False,
        trip_verbose: bool = False,
        progress: Optional[ProgressCallback] = None,
        palette: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        def _p(label: str, detail: Optional[str] = None) -> None:
            if progress is not None:
                try:
                    progress(label, detail)
                except Exception:
                    pass

        zone_id = building_info.get("id")
        if zone_id is None:
            raise ValueError("building_info に id (区画 ID) が必要です。")

        width = int(building_info.get("width") or building_info.get("position", {}).get("width") or 32)
        depth = int(building_info.get("depth") or building_info.get("position", {}).get("depth") or 32)
        # 下限を 28 に引き上げ、最大 max(width, depth) * 2 まで許容（96 cap は据え置き）。
        # 10x10 の小さな建物でも 28 voxel 解像度を確保してディテールが潰れないようにする。
        target_voxel = max(28, min(96, max(width, depth) * 2))

        mesh_base = f"mesh_{zone_id}"

        trip_meta: Dict[str, Any] = {}
        cached_paths = _mesh_cache_paths(self.fm.project_dir, zone_id)
        cached_mesh = _pick_mesh_cache(cached_paths)

        if force:
            _clear_mesh_cache(self.fm, zone_id)
            cached_mesh = None

        if cached_mesh is None:
            _p("① 画像を Tripo3D に送信", "GLB 生成タスクを作成しています")
            client = TripoClient()
            task_id = client.create_image_task(image_path)
            trip_meta["task_id"] = task_id
            _p("② Tripo3D で 3D メッシュを生成中", f"task_id = {task_id}（推定 60〜120 秒）")
            task = client.wait_for_task(task_id, verbose=trip_verbose)
            try:
                self.fm.save_json(f"tripo_task_{zone_id}.json", task)
            except (TypeError, ValueError):
                trip_meta["task_dump_skipped"] = "not JSON-serializable"
            else:
                trip_meta["task_dump"] = f"tripo_task_{zone_id}.json"

            url = TripoClient.model_url_from_task(task)
            trip_meta["model_url"] = url
            _p("③ GLB をダウンロード", os.path.basename(url) if url else None)
            mesh_path = client.download_model(url, self.fm.project_dir, mesh_base)
            trip_meta["saved_path"] = mesh_path
            trip_meta["saved_ext"] = os.path.splitext(mesh_path)[1].lower()
        else:
            mesh_path = cached_mesh
            trip_meta["cached_mesh"] = mesh_path
            trip_meta["cached_ext"] = os.path.splitext(mesh_path)[1].lower()
            _p("③ キャッシュ済み GLB を使用", os.path.basename(mesh_path))

        _p("④ メッシュを読み込み", os.path.basename(mesh_path))
        mesh = load_mesh(mesh_path)
        _p("⑤ ボクセル化", f"target voxel size = {target_voxel}")
        voxel_mesh = voxelize_mesh(mesh, target_size=target_voxel, constraint_axis="y")

        if palette:
            short = ", ".join(p.split(":", 1)[-1] for p in palette[:6])
            suffix = " ..." if len(palette) > 6 else ""
            _p("⑥ ブロック割当", f"テーマパレット {len(palette)} ブロック: {short}{suffix}")
        else:
            _p("⑥ ブロック割当", "色を Minecraft ブロックにマッチ中（デフォルトパレット）")
        assigner = BlockAssigner(palette=palette) if palette else BlockAssigner()
        # NOTE: BlockAssigner.assign_blocks の dithering は [0,255] スケール想定だが、
        # 内部の color は [0,1] スケールで渡されるため `ordered` を使うと値が飽和し、
        # 結果が "snow_block / black_concrete のチェッカー柄" になってしまう。
        # Mesh-First では色を素直にマッチさせたいので dithering=off / contextual=off を採用。
        assigned = assigner.assign_blocks(
            voxel_mesh,
            dithering="off",
            use_contextual=False,
            enable_smooth_blocks=False,
        )

        blocks = _assigned_to_blocks(assigned)
        blocks, y_shift = _normalize_ground(blocks)

        semantic_raw: Dict[str, Any] = {}
        if not skip_semantic:
            _p("⑦ Gemini で窓・ドア等を推定", f"voxel count = {len(blocks)}")
            try:
                semantic_raw = run_semantic_pass(image_path, blocks, building_info)
            except Exception as e:
                semantic_raw = {"error": str(e), "windows": [], "doors": [], "block_overrides": []}
        else:
            semantic_raw = {"windows": [], "doors": [], "block_overrides": []}

        bbox = _bbox_dict(blocks)
        semantic = clamp_semantic_to_bbox(semantic_raw, bbox)
        blocks = _merge_block_overrides(
            blocks, semantic.get("block_overrides") or [], palette=palette
        )

        _p("⑧ instructions を合成", f"{len(blocks)} blocks → 命令列")
        instructions = build_minimal_instructions(blocks, building_info, semantic)

        debug = {
            "mesh_path": mesh_path,
            "glb_path": mesh_path,
            "target_voxel_size": target_voxel,
            "voxel_count_before_merge": len(assigned),
            "y_normalization_shift": y_shift,
            "tripo": trip_meta,
            "semantic": semantic,
            "palette": list(palette) if palette else None,
        }
        if semantic_raw.get("raw_error"):
            debug["semantic_parse_error"] = semantic_raw["raw_error"]
        if semantic_raw.get("error"):
            debug["semantic_exception"] = semantic_raw["error"]

        return {
            "blocks": blocks,
            "instructions": instructions,
            "debug": debug,
        }
