"""
Mesh-First Architect: Tripo3D → GLB → ボクセル化 → BlockAssign → Gemini セマンティクス上書き。
"""
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional, Tuple

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


def _merge_block_overrides(
    blocks: List[Dict[str, Any]], overrides: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    idx: Dict[Tuple[int, int, int], int] = {}
    for i, b in enumerate(blocks):
        idx[(int(b["x"]), int(b["y"]), int(b["z"]))] = i
    for o in overrides:
        k = (int(o["x"]), int(o["y"]), int(o["z"]))
        blk = str(o["block"])
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
    ) -> Dict[str, Any]:
        zone_id = building_info.get("id")
        if zone_id is None:
            raise ValueError("building_info に id (区画 ID) が必要です。")

        width = int(building_info.get("width") or building_info.get("position", {}).get("width") or 32)
        depth = int(building_info.get("depth") or building_info.get("position", {}).get("depth") or 32)
        target_voxel = max(16, min(96, max(width, depth)))

        mesh_base = f"mesh_{zone_id}"

        trip_meta: Dict[str, Any] = {}
        cached_paths = _mesh_cache_paths(self.fm.project_dir, zone_id)
        cached_mesh = _pick_mesh_cache(cached_paths)

        if force:
            _clear_mesh_cache(self.fm, zone_id)
            cached_mesh = None

        if cached_mesh is None:
            client = TripoClient()
            task_id = client.create_image_task(image_path)
            trip_meta["task_id"] = task_id
            task = client.wait_for_task(task_id, verbose=trip_verbose)
            try:
                self.fm.save_json(f"tripo_task_{zone_id}.json", task)
            except (TypeError, ValueError):
                trip_meta["task_dump_skipped"] = "not JSON-serializable"
            else:
                trip_meta["task_dump"] = f"tripo_task_{zone_id}.json"

            url = TripoClient.model_url_from_task(task)
            trip_meta["model_url"] = url
            mesh_path = client.download_model(url, self.fm.project_dir, mesh_base)
            trip_meta["saved_path"] = mesh_path
            trip_meta["saved_ext"] = os.path.splitext(mesh_path)[1].lower()
        else:
            mesh_path = cached_mesh
            trip_meta["cached_mesh"] = mesh_path
            trip_meta["cached_ext"] = os.path.splitext(mesh_path)[1].lower()

        mesh = load_mesh(mesh_path)
        voxel_mesh = voxelize_mesh(mesh, target_size=target_voxel, constraint_axis="y")

        assigner = BlockAssigner()
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
            try:
                semantic_raw = run_semantic_pass(image_path, blocks, building_info)
            except Exception as e:
                semantic_raw = {"error": str(e), "windows": [], "doors": [], "block_overrides": []}
        else:
            semantic_raw = {"windows": [], "doors": [], "block_overrides": []}

        bbox = _bbox_dict(blocks)
        semantic = clamp_semantic_to_bbox(semantic_raw, bbox)
        blocks = _merge_block_overrides(blocks, semantic.get("block_overrides") or [])

        instructions = build_minimal_instructions(blocks, building_info, semantic)

        debug = {
            "mesh_path": mesh_path,
            "glb_path": mesh_path,
            "target_voxel_size": target_voxel,
            "voxel_count_before_merge": len(assigned),
            "y_normalization_shift": y_shift,
            "tripo": trip_meta,
            "semantic": semantic,
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
