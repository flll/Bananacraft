"""Step 1: Setup — プロジェクト作成 / 既存プロジェクトを開く。"""
from __future__ import annotations

import os

import streamlit as st

from ai.routing import AIStage, resolve_api_key_for_stage
from api_client import GeminiClient
from file_manager import FileManager
from v2.mesh_architect import MeshArchitect

from ui import state as S
from ui.buttons import primary_button
from ui.feature_card import FeatureCard, render_feature_cards


def _scan_existing_projects(base: str = "projects") -> list[str]:
    if not os.path.isdir(base):
        return []
    return sorted(
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d)) and not d.startswith(".")
    )


def _bootstrap_project(p_name: str) -> None:
    """新規 / 既存プロジェクトを開いて session_state を初期化する."""
    fm = FileManager(p_name)
    st.session_state.project_name = p_name
    st.session_state.file_manager = fm
    st.session_state.gemini_client = GeminiClient()
    st.session_state.chat_session = st.session_state.gemini_client.start_chat()

    try:
        st.session_state.architect = MeshArchitect(fm)
    except Exception as e:
        st.warning(f"Architect 初期化に失敗しました（後で再試行できます）: {e}")

    if fm.exists("concept_art.jpg") and fm.exists("concept_prompt_refined.txt"):
        reasoning = fm.load_text("concept_reasoning.txt") or ""
        refined = fm.load_text("concept_prompt_refined.txt") or ""
        st.session_state.concept = {
            "title": "Concept Art",
            "description": reasoning,
            "refined_prompt": refined,
            "image_path": os.path.join(fm.project_dir, "concept_art.jpg"),
        }

    if fm.exists("zoning_adjusted.json"):
        st.session_state.zoning = fm.load_json("zoning_adjusted.json")
    elif fm.exists("zoning_data.json"):
        st.session_state.zoning = fm.load_json("zoning_data.json")


def render() -> None:
    S.ensure_session_defaults()
    st.title("🛠️ Setup")
    st.caption("プロジェクトを作るか、既存のプロジェクトを開いて続きから作業します。")

    render_feature_cards(
        [
            FeatureCard(
                "🍌",
                "プロジェクトを丸ごと保存",
                "コンセプト・都市計画・建物データ・装飾プランが "
                "`projects/<name>/` 配下に自動保存されます。後から開けばその続きから。",
            ),
            FeatureCard(
                "🔑",
                "API キーはブラウザに記憶",
                "Gemini / OpenAI / Anthropic / Tripo3D のキーは "
                "Settings ページから登録できます。ブラウザの localStorage に保存され、次回も使えます。",
            ),
            FeatureCard(
                "🔁",
                "途中からやり直せる",
                "コンセプト・建物単位で何度でも再生成できるので、満足いくまで試行錯誤できます。",
                meta="所要時間: 全工程で 5〜10 分／建物",
            ),
        ]
    )
    st.divider()

    existing = _scan_existing_projects()
    tab_new, tab_open = st.tabs(["🆕 新規プロジェクト", f"📂 既存を開く（{len(existing)}）"])

    with tab_new:
        with st.form("project_init"):
            p_name = st.text_input(
                "プロジェクト名（半角英数推奨）",
                placeholder="Neo_Tokyo_2077",
                key="bnn_new_proj_name",
            )
            submitted = st.form_submit_button("プロジェクトを作成", type="primary")
            if submitted and p_name:
                _safe = p_name.strip()
                if not _safe:
                    st.error("プロジェクト名を入力してください。")
                else:
                    try:
                        resolve_api_key_for_stage(AIStage.IMAGE_RENDER)
                    except ValueError:
                        st.error(
                            "GEMINI_API_KEY が未設定です。左サイドバーまたは "
                            "Settings ページで設定してください。"
                        )
                        return
                    try:
                        _bootstrap_project(_safe)
                        st.toast(f"プロジェクト '{_safe}' を作成しました。", icon="🎉")
                        st.switch_page("pages_v2/concept.py")
                    except Exception as e:
                        st.error(f"初期化エラー: {e}")

    with tab_open:
        if not existing:
            st.info("まだプロジェクトがありません。「新規プロジェクト」タブから作成してください。", icon="📭")
        else:
            choice = st.selectbox(
                "開くプロジェクト",
                options=existing,
                index=0,
                key="bnn_open_proj_choice",
            )
            if primary_button("このプロジェクトを開く", key="bnn_open_proj_btn"):
                try:
                    _bootstrap_project(choice)
                    st.toast(f"プロジェクト '{choice}' を読み込みました。", icon="📂")
                    # 進捗に応じて次のステップに飛ばす
                    if S.has_zoning():
                        st.switch_page("pages_v2/city_plan.py")
                    elif S.has_concept():
                        st.switch_page("pages_v2/concept.py")
                    else:
                        st.switch_page("pages_v2/concept.py")
                except Exception as e:
                    st.error(f"プロジェクトを開けませんでした: {e}")


render()
