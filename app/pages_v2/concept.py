"""Step 2: Concept — コンセプト生成と反復改善。"""
from __future__ import annotations

import streamlit as st

from ai.routing import AIStage, Provider, effective_route

from ui import state as S
from ui.breadcrumbs import render_breadcrumbs
from ui.buttons import primary_button, secondary_button
from ui.feature_card import FeatureCard, render_feature_cards
from ui.stepper import derive_main_steps_state, render_top_stepper


def _require_project() -> bool:
    if not S.has_project() or st.session_state.get("file_manager") is None:
        st.warning(
            "先にプロジェクトを作成または開いてください。",
            icon="🛠️",
        )
        if primary_button("Setup へ移動", key="bnn_no_proj_setup"):
            st.switch_page("pages_v2/setup.py")
        return False
    return True


def _provider_spinner_label(stage: AIStage) -> str:
    r = effective_route(stage)
    if r.provider == Provider.GOOGLE:
        return "Gemini でコンセプトを洗練しています..."
    if r.provider == Provider.ANTHROPIC:
        return "Claude でコンセプトを洗練しています..."
    return "OpenAI でコンセプトを洗練しています..."


def _generate_concept(prompt: str) -> None:
    fm = st.session_state.file_manager
    client = st.session_state.gemini_client

    with st.spinner(_provider_spinner_label(AIStage.CONCEPT_BRAIN)):
        try:
            refined = client.refine_prompt(prompt)
        except Exception as e:
            st.error(f"Refinement Error: {e}")
            return
        reasoning = refined.get("reasoning", "")
        img_prompt = refined.get("image_prompt", prompt)

    with st.spinner("Nano Banana Pro で画像生成中..."):
        img_bytes = client.generate_image(img_prompt)
        if not img_bytes:
            st.error("画像生成に失敗しました。")
            return

    fm.save_text("concept_input.txt", prompt)
    fm.save_text("concept_reasoning.txt", reasoning)
    fm.save_text("concept_prompt_refined.txt", img_prompt)
    img_path = fm.save_image("concept_art.jpg", img_bytes)

    st.session_state.concept = {
        "title": "Concept Art",
        "description": reasoning,
        "refined_prompt": img_prompt,
        "image_path": img_path,
    }
    st.toast("コンセプトを生成しました！", icon="🎨")
    st.rerun()


def _refine_concept(feedback: str) -> None:
    fm = st.session_state.file_manager
    client = st.session_state.gemini_client
    with st.spinner("Refining based on feedback..."):
        try:
            refined = client.refine_prompt(f"修正指示: {feedback}")
        except Exception as e:
            st.error(f"Refinement Error: {e}")
            return
        reasoning = refined.get("reasoning", "")
        img_prompt = refined.get("image_prompt", "")

    with st.spinner("Repainting..."):
        new_bytes = client.generate_image(img_prompt)
        if not new_bytes:
            st.error("再生成に失敗しました。")
            return

    ts = fm._get_timestamp()
    fm.save_text(f"concept_feedback_{ts}.txt", feedback)
    fm.save_text(f"concept_reasoning_{ts}.txt", reasoning)
    fm.save_text(f"concept_prompt_{ts}.txt", img_prompt)
    new_path = fm.save_image(f"concept_art_{ts}.jpg", new_bytes)
    st.session_state.concept["description"] = reasoning
    st.session_state.concept["refined_prompt"] = img_prompt
    st.session_state.concept["image_path"] = new_path
    st.toast("修正案を生成しました。", icon="🪄")
    st.rerun()


def render() -> None:
    S.ensure_session_defaults()
    steps = derive_main_steps_state(
        has_project=S.has_project(),
        has_concept=S.has_concept(),
        has_zoning=S.has_zoning(),
        has_blueprint_for_selected=S.has_blueprint_for_selected(),
    )
    render_top_stepper("concept", completed=steps["completed"])

    if not _require_project():
        return

    render_breadcrumbs(
        [
            (f"📁 {st.session_state.project_name}", False),
            ("Concept", True),
        ]
    )
    st.title("💡 Step 2 — Concept")
    st.caption("一文の説明から、AI が街の世界観をビジュアル化します。気に入るまで何度でも作り直せます。")

    if not st.session_state.get("concept"):
        render_feature_cards(
            [
                FeatureCard(
                    "✏️",
                    "1 行で世界観を伝える",
                    "「魔法使いが住むかっこいいお城」のように書くだけで、"
                    "建物のスタイル・色・雰囲気を AI が決めてくれます。",
                ),
                FeatureCard(
                    "🎨",
                    "コンセプトアートを自動生成",
                    "Gemini Nano Banana Pro が高品質なコンセプトアートを描き、"
                    "後の都市計画と建物デザインに使う参照画像になります。",
                    meta="所要時間: 約 30 秒〜1 分",
                ),
                FeatureCard(
                    "🔁",
                    "フィードバックで反復",
                    "「もっと暗く」「夜にして」などの追加指示で画像を更新。"
                    "気に入るまで何度でも試せます。",
                ),
            ]
        )
        st.divider()

        prompt = st.text_area(
            "街のコンセプトを 1〜3 文で入力",
            height=120,
            placeholder="例：魔法使いが住むかっこいいお城。霧の立ちこめる森の中、紫と金の塔がそびえる。",
            key="bnn_concept_prompt",
        )
        c_gen, _ = st.columns([1, 3])
        with c_gen:
            if primary_button("✨ コンセプトを生成", key="bnn_concept_gen", disabled=not prompt.strip()):
                _generate_concept(prompt.strip())
        return

    # ---- Concept ある場合：表示 + フィードバック ----
    concept = st.session_state.concept
    c1, c2 = st.columns([2, 1])
    with c1:
        st.image(concept["image_path"], caption="Generated Concept", use_container_width=True)
        with st.expander("Gemini の思考プロセス (Detail)", expanded=True):
            st.write(concept.get("description", ""))
        with st.expander("生成プロンプト (Internal)", expanded=False):
            st.code(concept.get("refined_prompt", ""))

    with c2:
        st.subheader("Feedback Loop")
        feedback = st.text_area(
            "修正指示",
            placeholder="例：もっと不気味にして。夜にして。",
            key="bnn_concept_fb",
        )
        if secondary_button(
            "🪄 修正案を再生成",
            key="bnn_concept_refine",
            disabled=not feedback.strip(),
        ):
            _refine_concept(feedback.strip())

        st.divider()
        st.markdown(
            "気に入ったら、次のステップで AI が**コンセプトを実際の街の配置（建物・道路・広場）に落とし込みます**。"
        )
        if primary_button(
            "✅ コンセプト承認 → 都市計画へ",
            key="bnn_concept_approve",
            use_container_width=True,
        ):
            st.switch_page("pages_v2/city_plan.py")


render()
