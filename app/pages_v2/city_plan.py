"""Step 3: City Plan — ゾーニング・インフラ生成・建物選択."""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st

from rcon_client import RconClient
from v2.carpenter import CarpenterSession
from v2.city_planner import CityPlanner
from v2.zoning_fixer import fix_zoning

from ui import state as S
from ui.buttons import primary_button, secondary_button
from ui.feature_card import FeatureCard, render_feature_cards


def _require_concept() -> bool:
    if not S.has_project() or st.session_state.get("file_manager") is None:
        st.warning("先にプロジェクトを作成してください。", icon="🛠️")
        if primary_button("Setup へ", key="bnn_cp_no_proj"):
            st.switch_page("pages_v2/setup.py")
        return False
    if not S.has_concept():
        st.warning("先にコンセプトを生成してください。", icon="💡")
        if primary_button("Concept へ", key="bnn_cp_no_concept"):
            st.switch_page("pages_v2/concept.py")
        return False
    return True


def _generate_zoning() -> None:
    fm = st.session_state.file_manager
    client = st.session_state.gemini_client
    concept = st.session_state.concept or {}
    parts: list[str] = []
    if concept.get("description"):
        parts.append("【コンセプト思考】\n" + str(concept["description"]))
    if concept.get("refined_prompt"):
        parts.append("【画像生成プロンプト】\n" + str(concept["refined_prompt"]))
    if fm.exists("concept_input.txt"):
        cin = fm.load_text("concept_input.txt")
        if cin:
            parts.append("【ユーザー初期入力】\n" + cin)
    ctx = "\n\n".join(parts)

    with st.spinner("AI が建物の配置（ゾーニング）を計算中..."):
        try:
            zoning_data = client.generate_zoning_json(ctx)
            zoning_data = fix_zoning(zoning_data)
            st.session_state.zoning = zoning_data
            fm.save_json("zoning_data.json", zoning_data)
            st.toast("ゾーニングが完成しました！", icon="🗺️")
            st.rerun()
        except Exception as e:
            st.error(f"Zoning Generation Error: {e}")


def _render_zoning_map() -> None:
    zoning = st.session_state.zoning
    fm = st.session_state.file_manager
    buildings = S.get_zoning_buildings()
    if not buildings:
        st.warning("Zoning JSON に建物データがありません。")
        return

    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import matplotlib.colors as mcolors

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 200)
    ax.set_ylim(200, 0)
    ax.set_aspect("equal")
    ax.set_xlabel("X Block")
    ax.set_ylabel("Z Block")
    ax.grid(True, linestyle="--", alpha=0.3)

    theme = zoning.get("theme", "Urban Plan") if isinstance(zoning, dict) else "Urban Plan"
    ax.set_title(f"City Layout — {theme}")

    frame = patches.Rectangle((0, 0), 200, 200, linewidth=2, edgecolor="black", facecolor="#1A1108")
    ax.add_patch(frame)

    if fm.exists("infrastructure.json"):
        for item in fm.load_json("infrastructure.json") or []:
            tool = item.get("tool_name", "")
            params = item.get("parameters", {})
            if tool == "draw_road":
                start = params.get("start", [0, 0])
                end = params.get("end", [0, 0])
                width = params.get("width", 3)
                ax.plot(
                    [start[0], end[0]], [start[1], end[1]],
                    color="gray", linewidth=width, alpha=0.6, solid_capstyle="round",
                )
            elif tool == "fill_zone":
                rect = patches.Rectangle(
                    (params.get("x", 0), params.get("z", 0)),
                    params.get("width", 1), params.get("depth", 1),
                    linewidth=0,
                    facecolor=("green" if "grass" in params.get("material", "") else "lightgray"),
                    alpha=0.3,
                )
                ax.add_patch(rect)

    colors = list(mcolors.TABLEAU_COLORS.values())
    for i, b in enumerate(buildings):
        pos = b.get("position", {})
        x = pos.get("x", 0)
        z = pos.get("z", 0)
        w = pos.get("width", 10)
        d = pos.get("depth", 10)
        color = "gold" if b.get("type") == "landmark" else colors[i % len(colors)]
        ax.add_patch(patches.Rectangle((x, z), w, d, linewidth=1, edgecolor="black", facecolor=color, alpha=0.7))
        ax.text(
            x + w / 2, z + d / 2, str(i + 1),
            fontsize=10, ha="center", va="center", color="white", fontweight="bold",
        )

    st.pyplot(fig)


def _render_infrastructure_controls() -> None:
    fm = st.session_state.file_manager
    zoning = st.session_state.zoning
    has_plan = fm.exists("infrastructure.json")

    st.subheader("インフラ（道路・広場）")
    st.caption("AI が建物の間に通る道路や広場を提案します。Minecraft サーバー上に直接設置できます。")

    ic1, ic2 = st.columns(2)
    with ic1:
        gen_label = "🛣️ インフラを再生成" if has_plan else "🛣️ インフラを生成"
        if secondary_button(gen_label, key="bnn_cp_gen_infra"):
            with st.spinner("City Planner が道路と広場を設計中..."):
                try:
                    planner = CityPlanner()
                    concept_text = (st.session_state.concept or {}).get("description", "")
                    infra_plan = planner.generate_infrastructure(zoning, concept_text)
                    infra_json = [i.to_dict() for i in infra_plan]
                    fm.save_json("infrastructure.json", infra_json)
                    st.success(f"インフラプランを生成しました（{len(infra_json)} ステップ）")
                    st.rerun()
                except Exception as e:
                    st.error(f"Planning Error: {e}")

    with ic2:
        if has_plan:
            if secondary_button("🚜 サーバーに設置（RCON）", key="bnn_cp_build_infra"):
                with st.spinner("Terraforming..."):
                    try:
                        plan = fm.load_json("infrastructure.json")
                        ox, oy, oz = S.project_origin()
                        st.info(f"Building Infrastructure at Origin: ({ox}, {oy}, {oz})")
                        session = CarpenterSession(origin=(ox, oy, oz))
                        blocks = session.build_from_json(plan)
                        rcon = RconClient()
                        rcon.build_voxels(blocks, origin=(0, 0, 0))
                        st.success(f"インフラ建設完了！（{len(blocks)} blocks）")
                    except Exception as e:
                        st.error(f"Construction Error: {e}")
        else:
            st.caption("先にインフラを生成してください。")


def _render_building_list() -> None:
    fm = st.session_state.file_manager
    buildings = S.get_zoning_buildings()

    st.subheader("🏛️ Building List")
    st.caption(
        "建物カードをクリックすると、その建物のデザイン・建設・装飾ページに移動します。"
        "完了済みの建物は緑バッジが付きます。"
    )

    cols = st.columns(3)
    for i, b in enumerate(buildings):
        with cols[i % 3]:
            with st.container(border=True):
                thumb = f"design_{b['id']}_decorated.jpg"
                blocks_done = fm.exists(f"building_{b['id']}_blocks_v2.json")
                deco_done = fm.exists(f"building_{b['id']}_decoration.json")
                if fm.exists(thumb):
                    st.image(os.path.join(fm.project_dir, thumb), use_container_width=True)
                else:
                    st.markdown(
                        '<div style="height:120px;display:flex;align-items:center;'
                        'justify-content:center;background:rgba(255,255,255,0.03);'
                        'border-radius:8px;color:#8B7355;">未デザイン</div>',
                        unsafe_allow_html=True,
                    )

                pill_html = ""
                if deco_done:
                    pill_html = '<span class="bnn-pill bnn-pill-done">完成</span>'
                elif blocks_done:
                    pill_html = '<span class="bnn-pill bnn-pill-cur">設計済み</span>'
                else:
                    pill_html = '<span class="bnn-pill bnn-pill-todo">未着手</span>'
                st.markdown(f"**{i + 1}. {b['name']}** {pill_html}", unsafe_allow_html=True)
                st.caption(f"{b.get('type', 'normal')} | ({b['position']['x']}, {b['position']['z']})")

                btn_label = "▶ 続きから" if blocks_done else "🎨 デザインする"
                if primary_button(
                    btn_label,
                    key=f"bnn_pick_{b['id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_building = b
                    st.session_state.design_images = None
                    st.switch_page("pages_v2/building.py")


def render() -> None:
    S.ensure_session_defaults()
    if not _require_concept():
        return

    st.title("🗺️ City Plan")
    st.caption("コンセプトをもとに、建物の配置・道路・広場を AI が設計します。")

    if not S.has_zoning():
        render_feature_cards(
            [
                FeatureCard(
                    "🧭",
                    "建物配置を AI が設計",
                    "コンセプトに基づき、ランドマーク・住宅・商業など複数タイプの建物を 200×200 の街に配置します。",
                    meta="所要時間: 約 30 秒",
                ),
                FeatureCard(
                    "🛣️",
                    "道路と広場も自動生成",
                    "建物の間を結ぶ道路・芝の広場・砂利の中庭などを AI が決定。RCON で Minecraft に直接設置できます。",
                ),
                FeatureCard(
                    "🏗️",
                    "建物ごとに別々のデザイン",
                    "各建物カードから個別ページに入り、画像生成 → 3D 化 → ボクセル化 → 装飾までできます。",
                ),
            ]
        )
        st.divider()
        if primary_button("🧭 ゾーニングを生成", key="bnn_cp_gen_zoning"):
            _generate_zoning()
        return

    _render_zoning_map()
    st.divider()
    _render_infrastructure_controls()
    st.divider()
    _render_building_list()


render()
