"""初回起動時のオンボーディングモーダル。

localStorage `bananacraft_onboarding_v2 = "seen"` で記憶し、2 回目以降は表示しない。
"""
from __future__ import annotations

import streamlit as st


_LS_KEY = "bananacraft_onboarding_v2"


def _read_onboarding_flag() -> str:
    try:
        from streamlit_js_eval import streamlit_js_eval
    except ImportError:
        return ""
    try:
        v = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{_LS_KEY}') || ''",
            want_output=True,
            key="bnn_onboarding_read",
        )
        return v or ""
    except Exception:
        return ""


def _write_onboarding_flag() -> None:
    try:
        from streamlit_js_eval import streamlit_js_eval
    except ImportError:
        return
    try:
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{_LS_KEY}', 'seen')",
            want_output=False,
            key="bnn_onboarding_write",
        )
    except Exception:
        pass


def maybe_show_onboarding() -> None:
    """まだ表示していなければモーダルを開く。"""
    if st.session_state.get("_bnn_onb_done"):
        return
    # localStorage を読む（初回 None → 'seen' に書き込まれた後は 'seen'）
    if not st.session_state.get("_bnn_onb_checked"):
        flag = _read_onboarding_flag()
        st.session_state["_bnn_onb_flag"] = flag
        st.session_state["_bnn_onb_checked"] = True
    if st.session_state.get("_bnn_onb_flag") == "seen":
        st.session_state["_bnn_onb_done"] = True
        return

    if not st.session_state.get("_bnn_onb_open"):
        st.session_state["_bnn_onb_open"] = True

    if st.session_state.get("_bnn_onb_open"):
        @st.dialog("Welcome to Bananacraft 🍌🍯")  # type: ignore[misc]
        def _dlg() -> None:
            st.markdown(
                """
**AI で街を、建物を、装飾までまるごとデザインする 4 ステップワークフローです。**

| ステップ | 何をする | 所要時間 |
|---|---|---|
| **1. Setup** | プロジェクト名を決める | 5 秒 |
| **2. Concept** | 「魔法使いの城」など一文を入れ、AI がコンセプトアートを生成 | 30 秒〜1 分 |
| **3. City Plan** | コンセプトから建物配置をAIが提案、道路や広場も自動生成 | 30 秒〜1 分 |
| **4. Building** | 個別の建物を Tripo3D で 3D 化 → Minecraft ブロックに変換 → サーバーに設置 → AI が窓やランタンを装飾 | 建物 1 個あたり 2〜5 分 |

進行は画面上部のステッパーで一目瞭然。途中でも `City Plan` に戻って別の建物を選べます。
                """,
            )
            st.info(
                "API キー（Gemini / OpenAI / Anthropic / Tripo3D）は左サイドバー下部の "
                "「Settings」ページから設定できます。",
                icon="🔑",
            )
            if st.button("はじめる", type="primary", use_container_width=True, key="bnn_onb_close"):
                st.session_state["_bnn_onb_open"] = False
                st.session_state["_bnn_onb_done"] = True
                _write_onboarding_flag()
                st.rerun()

        _dlg()
