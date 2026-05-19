"""Bananacraft — 薄いエントリポイント。

`st.navigation` でマルチページ化されており、実体は `app/pages_v2/` 配下にある。
"""
from __future__ import annotations

import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# `app/` を sys.path に追加（`streamlit run app/main.py` 起動でも import 可能に）
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.append(_current_dir)

# ---- Page config（最初に呼ぶ必要がある）-------------------------------
st.set_page_config(
    page_title="Bananacraft",
    page_icon="🍌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Authentication ---------------------------------------------------
def _check_password() -> bool:
    password = os.getenv("STREAMLIT_PASSWORD")
    if not password:
        return True
    if st.session_state.get("password_correct", False):
        return True
    st.write("# 🔒 Login Required")
    p = st.text_input("Password", type="password", key="password_input")
    if st.button("Login", type="primary"):
        if p == password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password incorrect")
    return False


if not _check_password():
    st.stop()

# ---- Common state / theme --------------------------------------------
from ui.state import ensure_session_defaults, hydrate_api_keys_from_browser, apply_api_keys_to_env
from ui.theme import inject_theme_css
from ui.onboarding import maybe_show_onboarding
from v2 import mc_assets_prefs as _mc_prefs
from v2 import mc_assets_runtime as _mc_runtime

ensure_session_defaults()
hydrate_api_keys_from_browser()
apply_api_keys_to_env()
inject_theme_css()

_mc_runtime.set_force_procedural(_mc_prefs.load().force_procedural)
_mc_runtime.kickoff()

# ---- Sidebar (global) -------------------------------------------------
with st.sidebar:
    st.markdown("## 🍌 Bananacraft")
    st.caption("AI 都市開発システム")
    pname = st.session_state.get("project_name") or "—"
    st.markdown(f"**Project:** `{pname}`")
    if st.session_state.get("file_manager") is not None:
        from ui.state import project_origin
        ox, oy, oz = project_origin()
        st.markdown(f"**Origin:** `({ox}, {oy}, {oz})`")
    st.divider()
    st.caption("API キー・Origin・Terraformer の設定は **Settings** ページに集約されています。")

# ---- Navigation -------------------------------------------------------
pages = [
    st.Page("pages_v2/setup.py",     title="1. Setup",     icon="🛠️", default=True,  url_path="setup"),
    st.Page("pages_v2/concept.py",   title="2. Concept",   icon="💡",                  url_path="concept"),
    st.Page("pages_v2/city_plan.py", title="3. City Plan", icon="🗺️",                 url_path="city-plan"),
    st.Page("pages_v2/building.py",  title="4. Building",  icon="🏛️",                 url_path="building"),
    st.Page("pages_v2/settings.py",  title="Settings",     icon="⚙️",                 url_path="settings"),
]

nav = st.navigation(pages, position="sidebar")

# Onboarding (1 度だけ)
maybe_show_onboarding()

# 選択されたページを実行
nav.run()
