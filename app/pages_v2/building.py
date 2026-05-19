"""Building — 個別建物の Design → Blueprint → Build → Decorate。

各サブセクションの見出しにインラインの状態ピルを表示して進捗を伝える。
"""
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional

import streamlit as st

from rcon_client import RconClient
from v2.blueprint_analyzer import BlueprintAnalyzer
from v2.carpenter import CarpenterSession
from v2.decorator import Decorator
from v2.glb_viewer import find_glb_in_dir, render_glb, render_glb_bytes
from v2 import mc_assets_runtime as _mc_runtime
from v2.mesh_architect import MeshArchitect
from v2.palette_inference import infer_palette
from v2.preview import create_3d_preview
from v2.texture_atlas import get_or_build_atlas_png
from v2.voxel_glb_builder import build_voxel_glb
from voxelizer.block_assigner import BlockAtlas

from ui import state as S
from ui.buttons import danger_button, primary_button, secondary_button
from ui.feature_card import FeatureCard, render_feature_cards
from ui.status_card import PipelineStatus


# ---- Helpers ----------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _shared_block_atlas() -> BlockAtlas:
    """`BlockAtlas` を Streamlit セッション横断で 1 度だけロードする。"""
    return BlockAtlas()


@st.cache_data(show_spinner=False)
def _build_voxel_glb_cached(
    blocks_key: tuple,
    blocks_payload: list,
    atlas_version: str,
) -> bytes:
    """ブロック列ハッシュ + atlas バージョンをキーに GLB を生成・キャッシュ。

    `atlas_version` は ``official:<ver>`` / ``procedural`` のどちらか。
    公式アセット昇格時にキャッシュが自動的にミスして再生成される。
    """
    atlas = _shared_block_atlas()
    force = atlas_version == "procedural" and _mc_runtime.is_force_procedural()
    png = get_or_build_atlas_png(atlas, force_procedural=force)
    return build_voxel_glb(blocks_payload, atlas, png)


def _blocks_cache_key(blocks: List[Dict[str, Any]]) -> tuple:
    """同一内容なら同一タプル (順序非依存) になるキー。"""
    return tuple(sorted((int(b["x"]), int(b["y"]), int(b["z"]), b.get("type", "stone")) for b in blocks))


def _render_voxel_preview(
    blocks: List[Dict[str, Any]],
    zone: Dict[str, Any],
    zone_id: int,
) -> None:
    """Voxel タブの中身: GLB + テクスチャ。失敗時は Plotly にフォールバック。"""
    if not blocks:
        st.info("表示できるブロックがありません。")
        return

    try:
        key = _blocks_cache_key(blocks)
        atlas_tag = _mc_runtime.atlas_version_tag()
        glb_bytes = _build_voxel_glb_cached(key, blocks, atlas_tag)
        if atlas_tag.startswith("official:"):
            atlas_label = f"公式テクスチャ {atlas_tag.split(':', 1)[1]}"
        else:
            atlas_label = "手作りピクセルテクスチャ"
        ok = render_glb_bytes(
            glb_bytes,
            height=520,
            auto_rotate=False,
            alt=f"{zone.get('name', 'building')} voxel preview",
            caption=(
                f"📦 {len(blocks)} blocks · 1 cube/block · "
                f"{atlas_label} (320×320 atlas) — "
                f"{len(glb_bytes) / 1024:,.1f} KB"
            ),
        )
        if ok:
            return
    except Exception as e:  # noqa: BLE001 - フォールバックのため広く拾う
        st.warning(f"GLB preview に失敗したため Plotly にフォールバックします: {e}")

    fig = create_3d_preview(blocks, title=f"{zone['name']} (Voxel)")
    st.plotly_chart(fig, use_container_width=True)


def _force_persistent_leaves(blocks: List[Dict[str, Any]]) -> None:
    for b in blocks:
        t = b.get("type", "") if isinstance(b, dict) else ""
        if "leaves" in t and "persistent=true" not in t:
            b["type"] = (
                t.replace("]", ",persistent=true]") if "[" in t else f"{t}[persistent=true]"
            )


def _build_origin_for(zone: dict) -> tuple[int, int, int]:
    ox, oy, oz = S.project_origin()
    pos = zone.get("position", {})
    return (
        ox + int(pos.get("x", 0)),
        oy,
        oz + int(pos.get("z", 0)),
    )


def _restore_design_images(fm, zone_id: int) -> Optional[Dict[str, Optional[str]]]:
    dec = f"design_{zone_id}_decorated.jpg"
    stc = f"design_{zone_id}_structure.jpg"
    if not fm.exists(dec):
        return None
    return {
        "decorated": os.path.join(fm.project_dir, dec),
        "structure": os.path.join(fm.project_dir, stc) if fm.exists(stc) else None,
    }


def _zone_design_state(fm, zone_id: int) -> str:
    """`done` / `cur` / `todo` を返す."""
    if fm.exists(f"design_{zone_id}_structure.jpg"):
        return "done"
    if fm.exists(f"design_{zone_id}_decorated.jpg"):
        return "cur"
    return "todo"


def _zone_blueprint_state(fm, zone_id: int, design_done: bool) -> str:
    if fm.exists(f"building_{zone_id}_blocks_v2.json"):
        return "done"
    if not design_done:
        return "locked"
    return "cur"


def _zone_build_state(fm, zone_id: int, blueprint_done: bool, server_log_key: str) -> str:
    if not blueprint_done:
        return "locked"
    if st.session_state.get(server_log_key):
        return "done"
    return "cur"


def _zone_decorate_state(
    fm, zone_id: int, build_done: bool, executed_key: str
) -> str:
    has_plan = fm.exists(f"building_{zone_id}_decoration.json")
    if not build_done and not has_plan:
        return "locked"
    if st.session_state.get(executed_key):
        return "done"
    if has_plan:
        return "cur"
    return "cur" if build_done else "locked"


# ---- Section header with badge -----------------------------------------

def _section_header(num: int, title: str, state: str, detail: str = "") -> None:
    badge = {
        "done":   '<span class="bnn-pill bnn-pill-done">完了</span>',
        "cur":    '<span class="bnn-pill bnn-pill-cur">進行中</span>',
        "todo":   '<span class="bnn-pill bnn-pill-todo">未着手</span>',
        "locked": '<span class="bnn-pill bnn-pill-locked">前のステップ後</span>',
    }[state]
    suffix = (
        f' <span style="opacity:0.55;font-weight:400;font-size:0.8rem">— {detail}</span>'
        if detail else ""
    )
    st.markdown(f"#### {num}. {title} {badge}{suffix}", unsafe_allow_html=True)


# ---- Subsections ------------------------------------------------------

def _section_design(zone: dict) -> bool:
    """Returns True if design completed."""
    fm = st.session_state.file_manager
    client = st.session_state.gemini_client
    zone_id = zone["id"]

    if st.session_state.design_images is None:
        restored = _restore_design_images(fm, zone_id)
        if restored is not None:
            st.session_state.design_images = restored

    di = st.session_state.design_images
    has_dec = bool(di and di.get("decorated"))
    has_str = bool(di and di.get("structure"))

    st.caption(
        "コンセプトを参照しつつ、AI が建物のリファレンス画像（装飾あり / 構造のみの 2 種）を生成します。"
        "構造画像はあとで Tripo3D に渡して 3D メッシュに変換します。"
    )

    if not has_dec:
        prompt = st.text_area(
            "デザインプロンプト",
            value=f"{zone.get('description', '')} architecture, detailed",
            key=f"bnn_dgn_prompt_{zone_id}",
            height=80,
        )
        if primary_button(
            "🎨 デザイン画像を生成",
            key=f"bnn_dgn_gen_{zone_id}",
            disabled=not prompt.strip(),
        ):
            try:
                concept_bytes: Optional[bytes] = None
                if st.session_state.concept and st.session_state.concept.get("image_path"):
                    try:
                        with open(st.session_state.concept["image_path"], "rb") as f:
                            concept_bytes = f.read()
                    except Exception:
                        concept_bytes = None

                width = zone.get("position", {}).get("width", 10)
                depth = zone.get("position", {}).get("depth", 10)

                with st.spinner("Concept (装飾あり) を生成中..."):
                    dec_bytes = client.generate_concept_image(prompt, width, depth, concept_bytes)
                if not dec_bytes:
                    st.error("Concept 生成に失敗しました。")
                    return False
                dec_path = fm.save_image(f"design_{zone_id}_decorated.jpg", dec_bytes)
                st.session_state.design_images = {"decorated": dec_path, "structure": None}

                with st.spinner("Structure（装飾を除いた構造）を生成中..."):
                    str_bytes = client.generate_structure_image(dec_bytes)
                if str_bytes:
                    str_path = fm.save_image(f"design_{zone_id}_structure.jpg", str_bytes)
                    st.session_state.design_images["structure"] = str_path
                    st.toast("Design 完成！", icon="🖼️")
                    st.rerun()
                else:
                    st.error("Structure 生成に失敗しました。")
            except Exception as e:
                st.error(f"Generation Error: {e}")
        return False

    # 表示 + 修正
    t1, t2 = st.tabs(["✨ Concept", "🏗️ Structure"])
    with t1:
        st.image(di["decorated"], use_container_width=True)
    with t2:
        if has_str:
            st.image(di["structure"], use_container_width=True)
        else:
            st.info("Structure 画像を再生成してください。")

    with st.expander("デザインを修正する", expanded=False):
        prompt = st.text_area(
            "修正指示",
            placeholder="例：屋根を金色にしてもっと光らせて",
            key=f"bnn_dgn_fix_{zone_id}",
            height=80,
        )
        if secondary_button(
            "🪄 修正案を生成",
            key=f"bnn_dgn_refix_{zone_id}",
            disabled=not prompt.strip(),
        ):
            try:
                prev_path = (st.session_state.design_images or {}).get("decorated")
                prev_bytes = None
                if prev_path and os.path.exists(prev_path):
                    with open(prev_path, "rb") as f:
                        prev_bytes = f.read()

                base_desc = (zone.get("description") or "").strip()
                combined_desc = (
                    f"{base_desc}\n\n"
                    f"【ユーザーからの修正指示】\n{prompt.strip()}\n\n"
                    "【重要】添付の参照画像は、前回生成したMinecraftボクセル建築の現状です。"
                    "形状・配色・世界観・ブロック単位の質感は維持しつつ、修正指示の方向に寄せてください。"
                )
                width = zone["position"]["width"]
                depth = zone["position"]["depth"]

                with st.spinner("Minecraft ボクセル建築を修正中..."):
                    new_dec = client.generate_concept_image(
                        combined_desc, width, depth, prev_bytes
                    )
                if not new_dec:
                    st.error("再生成に失敗しました。")
                    return False
                ts = fm._get_timestamp()
                fm.save_text(f"design_{zone_id}_feedback_{ts}.txt", prompt.strip())
                p_path = fm.save_image(f"design_{zone_id}_dec_{ts}.jpg", new_dec)
                st.session_state.design_images["decorated"] = p_path
                st.toast("修正案を更新しました。", icon="🪄")
                st.rerun()
            except Exception as e:
                st.error(f"修正に失敗: {e}")

    return has_str


def _section_blueprint(zone: dict, design_done: bool) -> bool:
    fm = st.session_state.file_manager
    zone_id = zone["id"]
    inst_file = f"building_{zone_id}_instructions.json"
    blocks_file = f"building_{zone_id}_blocks_v2.json"
    mesh_glob = os.path.join(fm.project_dir, f"mesh_{zone_id}.*")

    st.caption(
        "Structure 画像から 3D メッシュを生成（Tripo3D）→ ボクセル化 → Minecraft ブロック割当を行います。"
        " さらに Gemini で窓・ドア等のセマンティック要素を補完します。"
    )

    if not design_done:
        st.info("先に Design ステップを完了してください。", icon="🔒")
        return False

    has_blocks = fm.exists(blocks_file)

    if has_blocks:
        blocks = fm.load_json(blocks_file) or []
        st.success(f"ブループリント準備済み: **{len(blocks)}** blocks", icon="✅")

        with st.expander("3D Preview", expanded=False):
            tab_vox, tab_glb = st.tabs(
                ["🧊 Voxel (Minecraft)", "🗿 Original Mesh (Tripo3D)"]
            )
            with tab_vox:
                _render_voxel_preview(blocks, zone, zone_id)
            with tab_glb:
                glb_path = find_glb_in_dir(fm.project_dir, zone_id)
                if glb_path:
                    render_glb(glb_path, height=520)
                else:
                    st.info(
                        "GLB ファイルが見つかりません。ブループリントを再生成すると "
                        "Tripo3D 由来のメッシュをここに表示できます。",
                        icon="📦",
                    )

        with st.expander("instructions.json", expanded=False):
            if fm.exists(inst_file):
                st.json(fm.load_json(inst_file), expanded=False)

        c1, c2 = st.columns(2)
        with c1:
            if danger_button(
                "🗑️ ブループリントを再生成",
                key=f"bnn_bp_regen_{zone_id}",
                confirm_title="ブループリントを作り直しますか？",
                confirm_body=(
                    "既存の `building_*_blocks_v2.json` と `instructions.json`、"
                    "および Tripo タスクのメタデータが削除されます。"
                    " GLB キャッシュは下のチェックボックスで指定したものに従います。"
                ),
                confirm_label="削除して再生成画面へ",
            ):
                for pth in glob.glob(mesh_glob):
                    if os.path.isfile(pth):
                        os.remove(pth)
                for fn in (inst_file, blocks_file, f"tripo_task_{zone_id}.json"):
                    pth = fm.get_path(fn)
                    if os.path.isfile(pth):
                        os.remove(pth)
                st.toast("ブループリントをクリアしました。", icon="🧹")
                st.rerun()
        return True

    force_tripo = st.checkbox(
        "Tripo を必ず再実行（GLB 再生成）",
        value=False,
        key=f"bnn_bp_force_{zone_id}",
        help="チェック時はキャッシュ GLB があっても Tripo に再依頼します（クレジット消費）。",
    )

    tripo_set = bool(os.environ.get("TRIPO_API_KEY", "").strip())
    if not tripo_set:
        st.error(
            "TRIPO_API_KEY が未設定です。Settings ページから登録するか、`.env` を編集してください。",
            icon="🔑",
        )

    if primary_button(
        "🏗️ ブループリントを作成 (Tripo + Voxel + Semantic)",
        key=f"bnn_bp_create_{zone_id}",
        disabled=not tripo_set,
    ):
        if not st.session_state.architect:
            st.session_state.architect = MeshArchitect(fm)
        arc: MeshArchitect = st.session_state.architect
        s_path = (st.session_state.design_images or {}).get("structure")
        if not s_path or not os.path.exists(s_path):
            st.error("Structure 画像が見つかりません。前のステップを完了してください。")
            return False
        b_info = {
            "id": zone_id,
            "name": zone["name"],
            "width": zone["position"]["width"],
            "depth": zone["position"]["depth"],
            "description": zone.get("description", ""),
            "facing": zone.get("facing", "south"),
        }
        try:
            with PipelineStatus(
                "Tripo3D で 3D メッシュを生成中…", expanded=True,
            ) as p:
                def _cb(label: str, detail: Optional[str]) -> None:
                    p.step(label)
                    if detail:
                        p.write(detail)

                concept_text = (st.session_state.concept or {}).get("description", "") or ""
                palette = infer_palette(concept_text, b_info)
                if palette:
                    short = ", ".join(b.split(":", 1)[-1] for b in palette[:6])
                    suffix = " ..." if len(palette) > 6 else ""
                    p.write(f"テーマパレット: {len(palette)} blocks → {short}{suffix}")

                tripo_cfg = st.session_state.get("tripo_config")
                if tripo_cfg is not None:
                    longest = max(int(b_info["width"]), int(b_info["depth"]))
                    lo = int(tripo_cfg.voxel_lower_bound)
                    hi = int(tripo_cfg.voxel_upper_bound)
                    if lo > hi:
                        lo, hi = hi, lo
                    est_voxel = max(lo, min(hi, longest))
                    if tripo_cfg.style:
                        style_label = (
                            f"{tripo_cfg.style} (stylize_model, "
                            f"block_size={tripo_cfg.style_block_size})"
                        )
                    else:
                        style_label = "なし"
                    p.write(
                        f"Tripo 設定: style={style_label} / face_limit={tripo_cfg.face_limit} "
                        f"/ geometry={tripo_cfg.geometry_quality}"
                    )
                    p.write(
                        f"ボクセル解像度: target_voxel≈{est_voxel} "
                        f"(lo={lo}, hi={hi}, footprint={longest})"
                    )
                    if tripo_cfg.use_texture_model:
                        p.write(
                            f"Texture Model: ON ({tripo_cfg.texture_model_version}, "
                            f"bake={tripo_cfg.texture_bake}) "
                            "→ 後段でテクスチャを再生成します（+クレジット / +時間）"
                        )

                result = arc.build_from_image(
                    s_path,
                    b_info,
                    force=bool(force_tripo),
                    progress=_cb,
                    palette=palette,
                    tripo_config=tripo_cfg,
                )
                blocks_out = result["blocks"]
                inst_out = result["instructions"]
                fm.save_json(blocks_file, blocks_out)
                fm.save_json(inst_file, inst_out)

                # ゾーン外形を結果に合わせて調整
                try:
                    from v2.layout_engine import LayoutEngine
                except ImportError:
                    from app.v2.layout_engine import LayoutEngine

                if S.has_zoning():
                    current = (
                        fm.load_json("zoning_adjusted.json")
                        if fm.exists("zoning_adjusted.json")
                        else fm.load_json("zoning_data.json")
                    )
                    engine = LayoutEngine(current)
                    updated = engine.update_zone_from_blocks(zone_id, blocks_out)
                    if updated:
                        engine.resolve_collisions(zone_id)
                        new_zoning = engine.get_zones()
                        fm.save_json("zoning_adjusted.json", new_zoning)
                        st.session_state.zoning = new_zoning
                        S.refresh_selected_from_zoning()

                p.done(f"完了：{len(blocks_out)} blocks / {len(inst_out)} 命令")
            st.toast("ブループリントが完成しました！", icon="🏗️")
            st.rerun()
        except Exception as e:
            st.error(f"Planning Error: {e}")
    return False


def _section_build(zone: dict, blueprint_done: bool, log_key: str) -> bool:
    fm = st.session_state.file_manager
    zone_id = zone["id"]
    blocks_file = f"building_{zone_id}_blocks_v2.json"
    build_origin = _build_origin_for(zone)
    current_origin = S.project_origin()

    st.caption("RCON 経由でブロックを一括設置します。`Origin` は Settings ページで変更できます。")

    st.markdown(
        f"**設置先座標**: `{build_origin}` "
        f"`(zoning offset = {zone['position']['x']}, {zone['position']['z']})`"
    )

    if not blueprint_done:
        st.info("先にブループリントを作成してください。", icon="🔒")
        return False

    c1, c2 = st.columns([2, 1])
    with c1:
        if primary_button("🚀 Instant Build", key=f"bnn_build_{zone_id}", use_container_width=True):
            try:
                with st.spinner(f"Building at {build_origin}..."):
                    rcon = RconClient()
                    blocks = fm.load_json(blocks_file)
                    _force_persistent_leaves(blocks)
                    log = rcon.build_voxels(blocks, origin=build_origin)
                st.session_state[log_key] = log
                st.toast(f"設置完了：{len(blocks)} blocks", icon="🚀")
                st.rerun()
            except Exception as e:
                st.error(f"Build Failed: {e}")

    with c2:
        if danger_button(
            "🗑️ エリアをクリア",
            key=f"bnn_clear_{zone_id}",
            confirm_title="この建物の範囲をクリアしますか？",
            confirm_body=(
                "Minecraft サーバー上の建物境界 + バッファを `fill air` でクリアします。"
                " 周囲の地形には影響しませんが、サーバー上のブロックは消えます。"
            ),
            confirm_label="クリアする",
        ):
            try:
                with st.spinner("Clearing area..."):
                    rcon = RconClient()
                    blocks = fm.load_json(blocks_file) or []
                    if blocks:
                        xs = [b["x"] for b in blocks]
                        ys = [b["y"] for b in blocks]
                        zs = [b["z"] for b in blocks]
                        ox, oy, oz = build_origin
                        x1 = ox + min(xs) - 2
                        x2 = ox + max(xs) + 2
                        z1 = oz + min(zs) - 2
                        z2 = oz + max(zs) + 2
                        y1 = current_origin[1]
                        y2 = y1 + (max(ys) - min(ys)) + 5
                    else:
                        x1 = build_origin[0]
                        z1 = build_origin[2]
                        x2 = x1 + zone["position"]["width"]
                        z2 = z1 + zone["position"]["depth"]
                        y1 = current_origin[1]
                        y2 = y1 + 100

                    cmds = [f"forceload add {x1} {z1} {x2} {z2}"]
                    y = y1
                    while y < y2:
                        y_end = min(y + 8, y2)
                        cmds.append(f"fill {x1} {y} {z1} {x2} {y_end} {z2} air")
                        y = y_end + 1
                    cmds.append(f"forceload remove {x1} {z1} {x2} {z2}")
                    rcon.connect_and_send(cmds)
                st.toast("クリアしました。", icon="🗑️")
            except Exception as e:
                st.error(f"Clear Failed: {e}")

    if st.session_state.get(log_key):
        with st.expander("Server Response Log", expanded=False):
            st.write(st.session_state[log_key])
        return True
    return False


def _section_decorate(zone: dict, build_done: bool, executed_key: str) -> None:
    fm = st.session_state.file_manager
    zone_id = zone["id"]
    deco_file = f"building_{zone_id}_decoration.json"

    st.caption(
        "Gemini が画像と構造を見比べて、窓・ドア・ランタン・蜂の巣などの装飾命令を生成し、"
        "AI Carpenter Bot（Mineflayer）が Minecraft 上に 1 ブロックずつ設置します。"
    )

    if not build_done:
        st.info("先に建物を設置してください。", icon="🔒")
        return

    has_plan = fm.exists(deco_file)

    cgen, _ = st.columns([1, 2])
    with cgen:
        gen_label = "🔁 装飾プランを再生成" if has_plan else "🎨 装飾プランを生成"
        if secondary_button(gen_label, key=f"bnn_deco_gen_{zone_id}"):
            try:
                with st.spinner("Gemini が装飾を分析中..."):
                    dec = Decorator()
                    concept = zone.get("description", "") or ""
                    if fm.exists("concept_reasoning.txt"):
                        concept += "\n" + (fm.load_text("concept_reasoning.txt") or "")
                    inst_file = f"building_{zone_id}_instructions.json"
                    instructions_data = fm.load_json(inst_file) if fm.exists(inst_file) else []
                    di = st.session_state.design_images or {}
                    image_path = di.get("decorated") or os.path.join(
                        fm.project_dir, f"design_{zone_id}_decorated.jpg"
                    )
                    if not image_path or not os.path.exists(image_path):
                        st.error("デザイン画像が見つかりません。Design ステップに戻ってください。")
                        return
                    b_info = {
                        "name": zone["name"],
                        "width": zone["position"]["width"],
                        "depth": zone["position"]["depth"],
                        "description": zone.get("description", ""),
                    }
                    deco_objs = dec.generate_decoration_plan(
                        image_path=image_path,
                        concept_text=concept,
                        structure_instructions=instructions_data,
                        building_info=b_info,
                    )
                    if not deco_objs:
                        st.error("装飾命令が生成できませんでした。")
                        return
                    deco_list = [i.to_dict() for i in deco_objs]
                    fm.save_json(deco_file, deco_list)
                    st.toast(f"装飾プラン完成！（{len(deco_list)} ステップ）", icon="🎨")
                    st.rerun()
            except Exception as e:
                st.error(f"Decoration Planning Failed: {e}")

    if not has_plan:
        return

    plan = fm.load_json(deco_file)
    st.caption(f"装飾プラン: **{len(plan)}** ステップ")
    with st.expander("装飾プランの JSON を表示", expanded=False):
        st.json(plan, expanded=False)

    cdep, _ = st.columns([1, 2])
    with cdep:
        if primary_button(
            "👷 AI Carpenter を起動して装飾する",
            key=f"bnn_deco_run_{zone_id}",
            use_container_width=True,
        ):
            try:
                with PipelineStatus("AI Carpenter Bot が装飾を設置中…", expanded=True) as p:
                    p.step("① 命令列をブロック化")
                    inst_file = f"building_{zone_id}_instructions.json"
                    inst_data = fm.load_json(inst_file) if fm.exists(inst_file) else []
                    analyzer = BlueprintAnalyzer(inst_data)
                    carpenter_temp = CarpenterSession(origin=(0, 0, 0))
                    deco_blocks = carpenter_temp.build_from_json(plan, analyzer=analyzer)

                    p.step("② Bot 用命令にフォーマット")
                    bot_instructions = []
                    for b in deco_blocks:
                        t = b["type"]
                        if "leaves" in t and "persistent=true" not in t:
                            t = t.replace("]", ",persistent=true]") if "[" in t else f"{t}[persistent=true]"
                        bot_instructions.append(
                            {"x": b["x"], "y": b["y"], "z": b["z"], "action": "setblock", "block": t}
                        )
                    bot_target = f"bot_instructions_{zone_id}.json"
                    fm.save_json(bot_target, {"instructions": bot_instructions})

                    p.step("③ Mineflayer Bot を起動", "Carpenter Bot が Minecraft に参加して設置中…")
                    cs = CarpenterSession()
                    build_origin = _build_origin_for(zone)
                    result_log = cs.run_bot(
                        project_name=st.session_state.project_name,
                        target_file=bot_target,
                        origin=build_origin,
                    )
                    p.done(f"完了：{len(bot_instructions)} 個の装飾を設置しました")
                st.session_state[executed_key] = result_log
                st.toast("装飾が完成しました！", icon="🎉")
                st.rerun()
            except Exception as e:
                st.error(f"Bot Execution Failed: {e}")

    if st.session_state.get(executed_key):
        with st.expander("Carpenter Bot Logs", expanded=False):
            st.code(st.session_state[executed_key])


# ---- Main render ------------------------------------------------------

def render() -> None:
    S.ensure_session_defaults()
    fm = st.session_state.get("file_manager")
    zone = st.session_state.get("selected_building")

    if not S.has_project() or fm is None:
        st.warning("先にプロジェクトを作成してください。", icon="🛠️")
        if primary_button("Setup へ", key="bnn_b_no_proj"):
            st.switch_page("pages_v2/setup.py")
        return
    if zone is None:
        st.warning("先に City Plan で建物を選んでください。", icon="🗺️")
        if primary_button("City Plan へ", key="bnn_b_no_sel"):
            st.switch_page("pages_v2/city_plan.py")
        return

    # 最新の zoning_adjusted を反映
    S.refresh_selected_from_zoning()
    zone = st.session_state.selected_building

    zone_id = zone["id"]
    server_log_key = f"_bnn_build_log_{zone_id}"
    bot_log_key = f"_bnn_bot_log_{zone_id}"

    st.title(f"🏛️ {zone['name']}")
    st.caption(f"{zone.get('type', 'normal')} | サイズ {zone['position']['width']}×{zone['position']['depth']}")

    design_state = _zone_design_state(fm, zone_id)
    bp_done = fm.exists(f"building_{zone_id}_blocks_v2.json")
    bp_state = _zone_blueprint_state(fm, zone_id, design_state == "done")
    build_state = _zone_build_state(fm, zone_id, bp_done, server_log_key)
    deco_state = _zone_decorate_state(fm, zone_id, build_state == "done", bot_log_key)

    sub_states = {"design": design_state, "blueprint": bp_state, "build": build_state, "decorate": deco_state}
    cur_key: Optional[str] = None
    for k in ("design", "blueprint", "build", "decorate"):
        if sub_states[k] != "done":
            cur_key = k
            break
    if cur_key is None:
        cur_key = "decorate"
    for k in list(sub_states):
        if sub_states[k] not in ("done", "locked") and k != cur_key:
            sub_states[k] = "todo"
        if k == cur_key and sub_states[k] not in ("done", "locked"):
            sub_states[k] = "cur"

    render_feature_cards(
        [
            FeatureCard(
                "🖼️→📐",
                "画像から正確な 3D 形状",
                "Tripo3D が Structure 画像から 3D メッシュを生成。"
                "従来の LLM ベースより細部まで再現されます。",
                meta="所要時間: 1〜3 分（API キャッシュあり）",
            ),
            FeatureCard(
                "🎨",
                "色合いも忠実に",
                "テクスチャから色をサンプリングして Minecraft のブロックパレット"
                "に最近傍マッチ。ハチミツ色なら蜂の巣や赤砂岩が選ばれます。",
            ),
            FeatureCard(
                "🤖",
                "装飾は AI Carpenter Bot",
                "Mineflayer で Bot がサーバーに入り、Gemini が指示した窓・ドア・ランタンを 1 個ずつ設置。",
            ),
        ]
    )
    st.divider()

    with st.container():
        _section_header(1, "デザイン画像を生成", sub_states["design"])
        design_done = _section_design(zone)

    st.divider()
    with st.container():
        _section_header(2, "Tripo3D + ボクセル化でブループリント作成", sub_states["blueprint"])
        bp_done_now = _section_blueprint(zone, design_done)

    st.divider()
    with st.container():
        _section_header(3, "Minecraft サーバーに設置", sub_states["build"])
        build_done_now = _section_build(zone, bp_done_now or bp_done, server_log_key)

    st.divider()
    with st.container():
        _section_header(4, "AI で装飾を追加", sub_states["decorate"])
        _section_decorate(zone, build_done_now or bool(st.session_state.get(server_log_key)), bot_log_key)

    st.divider()
    if secondary_button("⬅️ City Plan に戻る", key=f"bnn_b_back_{zone_id}"):
        st.switch_page("pages_v2/city_plan.py")


render()
