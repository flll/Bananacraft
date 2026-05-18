"""Settings — API キー / World Origin / Terraformer / プロジェクトリセット."""
from __future__ import annotations

import os

import streamlit as st

from ai.browser_keys import clear_persisted_keys, save_persisted_keys
from rcon_client import RconClient
from terraformer import Terraformer

from ui import state as S
from ui.buttons import danger_button, primary_button, secondary_button
from ui.feature_card import FeatureCard, render_feature_cards


def _section_api_keys() -> None:
    st.subheader("🔑 API キー")
    st.caption(
        "ブラウザの localStorage に保存できます。XSS のあるページではキーが漏洩しうるため、"
        "信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシを推奨します。"
    )
    ctx = st.session_state.api_key_context

    if "sb_gem" not in st.session_state and ctx.get("GEMINI_API_KEY"):
        st.session_state.sb_gem = ctx["GEMINI_API_KEY"]
    if "sb_oai" not in st.session_state and ctx.get("OPENAI_API_KEY"):
        st.session_state.sb_oai = ctx["OPENAI_API_KEY"]
    if "sb_ant" not in st.session_state and ctx.get("ANTHROPIC_API_KEY"):
        st.session_state.sb_ant = ctx["ANTHROPIC_API_KEY"]
    if "sb_tripo" not in st.session_state and ctx.get("TRIPO_API_KEY"):
        st.session_state.sb_tripo = ctx["TRIPO_API_KEY"]

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("GEMINI_API_KEY", type="password", key="sb_gem",
                      help="画像生成・コンセプト・ゾーニング・装飾分析")
        st.text_input("OPENAI_API_KEY", type="password", key="sb_oai",
                      help="フォールバック用 (Architect FC など)")
    with c2:
        st.text_input("ANTHROPIC_API_KEY", type="password", key="sb_ant",
                      help="フォールバック用 (コンセプト対話など)")
        st.text_input("TRIPO_API_KEY", type="password", key="sb_tripo",
                      help="画像から 3D メッシュ生成 (`tsk_` で始まる)")

    for wkey, env in (
        ("sb_gem", "GEMINI_API_KEY"),
        ("sb_oai", "OPENAI_API_KEY"),
        ("sb_ant", "ANTHROPIC_API_KEY"),
        ("sb_tripo", "TRIPO_API_KEY"),
    ):
        v = st.session_state.get(wkey, "")
        if isinstance(v, str) and v.strip():
            ctx[env] = v.strip()
    S.apply_api_keys_to_env()

    c_save, c_clr = st.columns(2)
    with c_save:
        if secondary_button("💾 ブラウザに保存", key="bnn_set_save_keys", use_container_width=True,
                            help="localStorage に書き込み"):
            try:
                save_persisted_keys(ctx)
                st.success("保存しました")
            except Exception as e:
                st.warning(str(e))
    with c_clr:
        if danger_button(
            "🗑️ ブラウザから削除",
            key="bnn_set_clear_keys",
            confirm_title="保存済み API キーを削除しますか？",
            confirm_body="localStorage と現在のセッションから API キーが消えます。次回また入力が必要です。",
            confirm_label="削除する",
            use_container_width=True,
        ):
            clear_persisted_keys()
            for wkey in ("sb_gem", "sb_oai", "sb_ant", "sb_tripo"):
                st.session_state.pop(wkey, None)
            st.session_state.api_key_context = {}
            st.session_state._browser_keys_hydrated = False
            S.apply_api_keys_to_env()
            st.toast("削除しました。", icon="🧹")
            st.rerun()


def _section_world_origin() -> None:
    st.subheader("🌍 Minecraft World Origin")
    st.caption("建設範囲の南西の原点ブロック。建物・インフラ・装飾の絶対座標はここに加算されます。")
    fm = st.session_state.get("file_manager")
    ox, oy, oz = S.project_origin()
    c1, c2, c3 = st.columns(3)
    with c1:
        n_x = st.number_input("Origin X", value=int(ox), key="bnn_set_ox")
    with c2:
        n_y = st.number_input("Origin Y", value=int(oy), key="bnn_set_oy")
    with c3:
        n_z = st.number_input("Origin Z", value=int(oz), key="bnn_set_oz")
    if primary_button("💾 Save Origin", key="bnn_set_save_origin",
                       disabled=fm is None):
        S.save_project_origin(int(n_x), int(n_y), int(n_z))
        st.toast("Saved!", icon="💾")


def _section_terraformer() -> None:
    st.subheader("🚜 Terraformer (Clear 200×200)")
    ox, oy, oz = S.project_origin()
    st.caption(f"Area: ({ox}, {oz}) to ({ox + 200}, {oz + 200}) at Y = {oy}")
    if danger_button(
        "🚜 Terraformer を実行",
        key="bnn_set_run_terra",
        confirm_title="200×200 エリアをクリアしますか？",
        confirm_body=(
            "サーバー上の指定エリアを `fill air` で平らにします。"
            "周囲の地形には影響しませんが、対象エリアの既存ブロックは消えます。"
        ),
        confirm_label="実行する",
    ):
        try:
            with st.spinner("Clearing area & Fixing chunks..."):
                rcon = RconClient()
                terra = Terraformer(rcon)
                logs = terra.terraform((int(ox), int(oy), int(oz)), width=200, depth=200, base_y=int(oy))
                st.success("Terraforming Complete!")
                with st.expander("Logs"):
                    st.write(logs)
        except Exception as e:
            st.error(f"Terraforming Failed: {e}")


def _section_project_management() -> None:
    if not S.has_project():
        return
    st.subheader("📁 プロジェクト")
    st.markdown(f"現在のプロジェクト: `{st.session_state.project_name}`")
    cc1, cc2 = st.columns(2)
    with cc1:
        if secondary_button("⬅️ プロジェクトを閉じる", key="bnn_set_close_proj"):
            S.reset_project()
            st.switch_page("pages_v2/setup.py")
    with cc2:
        if danger_button(
            "🗑️ Restart Project（全消去）",
            key="bnn_set_reset_proj",
            confirm_title="プロジェクトをリセットしますか？",
            confirm_body=(
                "セッション内の全ての状態（コンセプト・ゾーニング・選択中の建物など）が消えます。"
                "保存済みファイル（`projects/<name>/`）は残るので、再度開けば復元できます。"
            ),
            confirm_label="リセットする",
        ):
            S.reset_project()
            st.switch_page("pages_v2/setup.py")


def render() -> None:
    S.ensure_session_defaults()
    st.title("⚙️ Settings")
    st.caption("API キー・原点座標・サーバー操作などの裏方設定。")

    render_feature_cards(
        [
            FeatureCard("🔑", "API キーをまとめて管理",
                        "4 つのプロバイダー（Gemini / OpenAI / Anthropic / Tripo3D）"
                        "を一括設定。ブラウザ保存で次回も即使えます。"),
            FeatureCard("🌍", "建設地点を指定",
                        "Minecraft サーバー上のどこに建てるかを X/Y/Z で指定。"
                        "建物・インフラは全部この原点を基準に配置されます。"),
            FeatureCard("🚜", "地ならし",
                        "Terraformer で 200×200 のエリアを `fill air` クリアします。"
                        "ワールドの安全な位置で実行してください。"),
        ]
    )
    st.divider()
    _section_api_keys()
    st.divider()
    _section_world_origin()
    st.divider()
    _section_terraformer()
    st.divider()
    _section_project_management()


render()
