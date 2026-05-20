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
    from tripo_client import TripoClient, TripoClientError
    from voxelizer.mesh_loader import load_mesh
    from voxelizer.bvh_ray_voxelizer import voxelize_mesh
    from voxelizer.block_assigner import BlockAssigner
    from v2.semantic_pass import run_semantic_pass, clamp_semantic_to_bbox
    from v2.instructions_synthesizer import build_minimal_instructions
    from v2.tripo_config import TripoConfig
except ImportError:
    from app.file_manager import FileManager
    from app.tripo_client import TripoClient, TripoClientError
    from app.voxelizer.mesh_loader import load_mesh
    from app.voxelizer.bvh_ray_voxelizer import voxelize_mesh
    from app.voxelizer.block_assigner import BlockAssigner
    from app.v2.semantic_pass import run_semantic_pass, clamp_semantic_to_bbox
    from app.v2.instructions_synthesizer import build_minimal_instructions
    from app.v2.tripo_config import TripoConfig


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
    """キャッシュ済みメッシュから **mesh_loader が読める形式** を優先順位で選ぶ。

    FBX は voxelizer.mesh_loader が扱えないので、ローダーがサポートする
    拡張子のみに絞り込んでから優先順位を付ける。何も該当しなければ None
    （= 再ダウンロード）。
    """
    if not paths:
        return None
    order = {".glb": 0, ".gltf": 1, ".obj": 2, ".stl": 3, ".ply": 4}

    def sort_key(p: str) -> Tuple[int, float]:
        ext = os.path.splitext(p)[1].lower()
        return order[ext], -os.path.getmtime(p)

    loadable = [p for p in paths if os.path.splitext(p)[1].lower() in order]
    if not loadable:
        return None
    return sorted(loadable, key=sort_key)[0]


def _clear_mesh_cache(fm: FileManager, zone_id: Any) -> None:
    for p in _mesh_cache_paths(fm.project_dir, zone_id):
        try:
            os.remove(p)
        except OSError:
            pass
    aux_files = [
        f"tripo_task_{zone_id}.json",
        f"tripo_stylize_task_{zone_id}.json",
        f"tripo_texture_task_{zone_id}.json",
        f"building_{zone_id}.schem",
        f"building_{zone_id}_schem_meta.json",
    ]
    for fn in aux_files:
        p = fm.get_path(fn)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def _bbox_dict(blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    if not blocks:
        return {
            "min_x": 0, "max_x": 0,
            "min_y": 0, "max_y": 0,
            "min_z": 0, "max_z": 0,
        }
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
        tripo_config: Optional["TripoConfig"] = None,
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
        # 決定論的サイズ:
        # 底面 (max(width, depth)) をそのまま voxel 解像度に使う。建物の敷地と
        # ボクセル数が一致するので、再生成しても底面サイズが揃う。
        # voxel_lower_bound / voxel_upper_bound でユーザーが解像度を制御できる。
        # 1 voxel ≒ 1 Minecraft ブロックにしたいなら下限を 12 程度に下げる。
        lo = int(tripo_config.voxel_lower_bound) if tripo_config else 12
        hi = int(tripo_config.voxel_upper_bound) if tripo_config else 48
        if lo > hi:
            lo, hi = hi, lo
        target_voxel = max(lo, min(hi, max(width, depth)))

        mesh_base = f"mesh_{zone_id}"

        trip_meta: Dict[str, Any] = {}
        cached_paths = _mesh_cache_paths(self.fm.project_dir, zone_id)
        cached_mesh = _pick_mesh_cache(cached_paths)
        # schem 主軸経路で成功した場合のショートサーキット用フラグ。
        # True になると GLB ダウンロード／trimesh ボクセル化／semantic pass を
        # すべてスキップし、`{"blocks": [], "instructions": [], "schem_path": ...}`
        # を返す。
        schem_only_path = False

        if force:
            _clear_mesh_cache(self.fm, zone_id)
            cached_mesh = None

        if cached_mesh is None:
            _p("① 画像を Tripo3D に送信", "GLB 生成タスクを作成しています")
            client = TripoClient()
            if tripo_config is not None:
                task_kwargs = tripo_config.to_tripo_kwargs()
                trip_meta["tripo_config"] = {
                    "model_version": tripo_config.model_version,
                    "style": tripo_config.style,
                    "geometry_quality": tripo_config.geometry_quality,
                    "face_limit": tripo_config.face_limit,
                    "texture_quality": tripo_config.texture_quality,
                    "model_seed": tripo_config.model_seed,
                    "texture_seed": tripo_config.texture_seed,
                    "voxel_lower_bound": tripo_config.voxel_lower_bound,
                    "voxel_upper_bound": tripo_config.voxel_upper_bound,
                    "use_texture_model": tripo_config.use_texture_model,
                    "texture_model_version": tripo_config.texture_model_version,
                }
                task_id = client.create_image_task(image_path, **task_kwargs)
            else:
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

            base_url = TripoClient.model_url_from_task(task)
            trip_meta["base_model_url"] = base_url
            final_url = base_url
            final_task_id_for_download = task_id

            # --- Optional: stylize_model でポストプロセススタイル適用 ---
            if tripo_config is not None:
                stylize_kwargs = tripo_config.to_stylize_kwargs()
            else:
                stylize_kwargs = None
            if stylize_kwargs is not None:
                style_name = stylize_kwargs["style"]
                _p(
                    f"②.3 後処理スタイル適用 ({style_name})",
                    f"stylize_model: block_size={stylize_kwargs['block_size']}",
                )
                try:
                    style_task_id = client.create_stylize_task(
                        original_model_task_id=task_id,
                        **stylize_kwargs,
                    )
                    trip_meta["stylize_task_id"] = style_task_id
                    style_task = client.wait_for_task(style_task_id, verbose=trip_verbose)
                    try:
                        self.fm.save_json(f"tripo_stylize_task_{zone_id}.json", style_task)
                    except (TypeError, ValueError):
                        pass

                    # schem 経路: style=minecraft なら .schem を最優先で保存する。
                    # 保存成功時は schem を **主成果物** とし、GLB ボクセル化は走らせない。
                    # schem 保存に失敗、または stylize 自体がメッシュも返した場合は
                    # ベース GLB / stylize GLB に**フォールバック**してレガシー経路を走らせる。
                    if TripoClient.has_schem_output(style_task):
                        try:
                            schem_url = TripoClient.model_url_from_task(
                                style_task, prefer_schem=True
                            )
                            _p(
                                "②.4 .schem を保存（WorldEdit 配置用）",
                                os.path.basename(schem_url) if schem_url else None,
                            )
                            schem_path = client.download_schem(
                                schem_url,
                                self.fm.project_dir,
                                f"building_{zone_id}",
                            )
                            trip_meta["schem_url"] = schem_url
                            trip_meta["schem_path"] = schem_path
                            schem_meta = {
                                "source": "tripo_stylize",
                                "schem_path": os.path.basename(schem_path),
                                "tripo_task_id": style_task_id,
                                "stylize_style": stylize_kwargs["style"],
                                "stylize_block_size": stylize_kwargs["block_size"],
                            }
                            try:
                                self.fm.save_json(
                                    f"building_{zone_id}_schem_meta.json", schem_meta
                                )
                            except (TypeError, ValueError):
                                pass
                            schem_only_path = True
                            _p(
                                "②.5 schem 経路で完了（GLB ボクセル化をスキップ）",
                                "WorldEdit + RCON でワールドに配置できます",
                            )
                        except TripoClientError as schem_err:
                            trip_meta["schem_error"] = str(schem_err)
                            _p(
                                "②.4 .schem 保存に失敗（パイプラインは継続）",
                                str(schem_err),
                            )

                    if not schem_only_path:
                        try:
                            stylize_url = TripoClient.model_url_from_task(
                                style_task, mesh_only=True
                            )
                            final_url = stylize_url
                            trip_meta["stylize_model_url"] = final_url
                            final_task_id_for_download = style_task_id
                        except TripoClientError as e:
                            # stylize が .schem のみ返す → ベース GLB で続行
                            trip_meta["stylize_mesh_error"] = str(e)
                            final_url = base_url
                            final_task_id_for_download = task_id
                            _p("②.3 メッシュ無し（ベース GLB で続行）", str(e))
                except TripoClientError as e:
                    trip_meta["stylize_error"] = str(e)
                    final_url = base_url
                    final_task_id_for_download = task_id
                    _p("②.3 スタイル適用をスキップ（ベース GLB で続行）", str(e))

            # schem 経路で完了している場合はここで早期 return する
            if schem_only_path:
                return {
                    "blocks": [],
                    "instructions": [],
                    "schem_path": trip_meta.get("schem_path"),
                    "debug": {
                        "tripo": trip_meta,
                        "palette": list(palette) if palette else None,
                        "schem_only_path": True,
                    },
                }

            # --- Optional: Texture Model 後段精製 ---
            if tripo_config is not None and tripo_config.use_texture_model:
                _p(
                    "②.5 Texture Model で高品質テクスチャを再生成",
                    f"model_version = {tripo_config.texture_model_version}",
                )
                tex_kwargs = tripo_config.to_texture_kwargs()
                tex_task_id = client.create_texture_task(
                    original_model_task_id=task_id,
                    image_path=image_path,
                    **tex_kwargs,
                )
                trip_meta["texture_task_id"] = tex_task_id
                tex_task = client.wait_for_task(tex_task_id, verbose=trip_verbose)
                try:
                    self.fm.save_json(f"tripo_texture_task_{zone_id}.json", tex_task)
                except (TypeError, ValueError):
                    pass
                final_url = TripoClient.model_url_from_task(tex_task)
                trip_meta["texture_model_url"] = final_url
                final_task_id_for_download = tex_task_id

            trip_meta["model_url"] = final_url
            _p(
                "③ GLB をダウンロード",
                os.path.basename(final_url) if final_url else None,
            )
            mesh_path = client.download_model(final_url, self.fm.project_dir, mesh_base)
            trip_meta["saved_path"] = mesh_path
            trip_meta["saved_ext"] = os.path.splitext(mesh_path)[1].lower()
            trip_meta["download_source_task"] = final_task_id_for_download
        else:
            mesh_path = cached_mesh
            trip_meta["cached_mesh"] = mesh_path
            trip_meta["cached_ext"] = os.path.splitext(mesh_path)[1].lower()
            _p("③ キャッシュ済み GLB を使用", os.path.basename(mesh_path))

        _p("④ メッシュを読み込み", os.path.basename(mesh_path))
        mesh = load_mesh(mesh_path)

        # 決定論的サイズ正規化:
        # 同じ building_info で毎回同じ底面サイズになるよう、メッシュの水平
        # 寸法のうち長い方を constraint 軸に選ぶ。これで Tripo3D の出力寸法
        # に左右されず、`max(width, depth)` を底面の実サイズとして固定できる。
        dims = mesh.dimensions  # (x, y, z)
        if dims[0] >= dims[2]:
            constraint_axis = "x"
            constraint_label = "x (footprint width)"
        else:
            constraint_axis = "z"
            constraint_label = "z (footprint depth)"
        _p(
            "⑤ ボクセル化",
            f"target voxel size = {target_voxel} along {constraint_label}",
        )
        voxel_mesh = voxelize_mesh(
            mesh, target_size=target_voxel, constraint_axis=constraint_axis
        )

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

        # ボクセル化が空に終わったケース（解像度過小・メッシュ薄い等）の保護:
        # semantic_pass / instructions 合成は空配列でも動くが、ユーザーへの説明を
        # 明示するために早期に分岐ログだけ出しておく。
        if not blocks:
            _p(
                "⑦ ボクセル化結果が空",
                f"target voxel size = {target_voxel} は小さすぎる可能性があります。"
                " Settings の voxel_lower_bound を上げて再生成してください。",
            )

        semantic_raw: Dict[str, Any] = {}
        if blocks and not skip_semantic:
            _p("⑦ Gemini で窓・ドア等を推定", f"voxel count = {len(blocks)}")
            try:
                semantic_raw = run_semantic_pass(image_path, blocks, building_info)
            except Exception as e:
                semantic_raw = {"error": str(e), "windows": [], "doors": [], "block_overrides": []}
        else:
            semantic_raw = {"windows": [], "doors": [], "block_overrides": []}
            if not blocks:
                _p("⑦ semantic pass をスキップ", "blocks が空のため")

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
            "schem_path": trip_meta.get("schem_path"),
            "debug": debug,
        }
