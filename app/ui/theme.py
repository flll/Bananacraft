"""ハチミツ色のテーマ + 共通 CSS インジェクション。

config.toml で primaryColor などは設定済み。ここでは
`.bnn-*` 系のクラスを使ったカスタム CSS を毎描画で DOM に流し込む。
"""
from __future__ import annotations

import streamlit as st


_HONEY = "#F39C12"
_HONEY_DARK = "#B9770E"
_HONEY_SOFT = "#FCEAC4"
_DANGER = "#E74C3C"
_OK = "#27AE60"
_INK = "#0E0905"
_PAPER = "#1A1108"
_PAPER2 = "#2A1810"
_MUTED = "#8B7355"

_CSS = f"""<style>
/* ===== Bananacraft global tweaks ===== */
.stApp {{
    background:
        radial-gradient(1200px 600px at 80% -10%, rgba(243,156,18,0.10), transparent 60%),
        radial-gradient(900px 500px at -10% 110%, rgba(243,156,18,0.06), transparent 60%),
        {_PAPER};
    color: #FAFAFA;
}}

/* Headings */
h1, h2, h3 {{
    font-family: 'Helvetica Neue', 'Inter', sans-serif;
    font-weight: 800;
    letter-spacing: -0.02em;
}}
h1 {{ color: #FFE3A8; }}

/* Default st.button = secondary look. Real "primary" is opted in via class. */
.stButton > button[kind="secondary"],
.stButton > button:not([kind]) {{
    background: transparent;
    color: {_HONEY};
    border: 1.5px solid {_HONEY_DARK};
    border-radius: 8px;
    font-weight: 600;
    transition: all 120ms ease;
}}
.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind]):hover {{
    background: rgba(243,156,18,0.12);
    border-color: {_HONEY};
    color: #FFE3A8;
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(180deg, {_HONEY}, {_HONEY_DARK});
    color: {_INK};
    border: none;
    border-radius: 8px;
    font-weight: 800;
    box-shadow: 0 2px 8px rgba(243,156,18,0.35);
}}
.stButton > button[kind="primary"]:hover {{
    filter: brightness(1.08);
    box-shadow: 0 4px 14px rgba(243,156,18,0.45);
}}

/* ===== Stepper (top) ===== */
.bnn-stepper {{
    display: flex;
    align-items: center;
    gap: 0;
    margin: 0 0 1rem 0;
    padding: 0.75rem 1rem;
    background: linear-gradient(180deg, rgba(42,24,16,0.6), rgba(26,17,8,0.6));
    border: 1px solid rgba(243,156,18,0.18);
    border-radius: 12px;
}}
.bnn-step {{
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex: 1 1 0;
    color: {_MUTED};
    font-size: 0.95rem;
    font-weight: 600;
    white-space: nowrap;
}}
.bnn-step + .bnn-step::before {{
    content: "";
    flex: 1;
    height: 2px;
    margin: 0 0.55rem;
    background: linear-gradient(90deg, rgba(139,115,85,0.4), rgba(139,115,85,0.15));
    border-radius: 2px;
}}
.bnn-step.is-done {{ color: {_OK}; }}
.bnn-step.is-done + .bnn-step::before {{
    background: linear-gradient(90deg, {_OK}, rgba(243,156,18,0.5));
}}
.bnn-step.is-cur  {{ color: #FFE3A8; }}
.bnn-step .bnn-step-num {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(255,255,255,0.06);
    border: 1.5px solid rgba(139,115,85,0.5);
    color: inherit;
    font-weight: 800;
    font-size: 0.85rem;
}}
.bnn-step.is-done .bnn-step-num {{
    background: {_OK};
    border-color: {_OK};
    color: {_INK};
}}
.bnn-step.is-cur .bnn-step-num {{
    background: {_HONEY};
    border-color: {_HONEY};
    color: {_INK};
    box-shadow: 0 0 0 4px rgba(243,156,18,0.18);
}}

/* ===== Vertical sub-stepper ===== */
.bnn-substep {{
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    padding: 0.55rem 0.75rem;
    margin: 0.25rem 0;
    border-left: 3px solid rgba(139,115,85,0.35);
    border-radius: 0 8px 8px 0;
    background: rgba(255,255,255,0.02);
    color: {_MUTED};
}}
.bnn-substep.is-done {{
    border-left-color: {_OK};
    color: #C6E5C9;
}}
.bnn-substep.is-cur {{
    border-left-color: {_HONEY};
    background: rgba(243,156,18,0.08);
    color: #FFE3A8;
}}
.bnn-substep.is-locked {{ opacity: 0.5; }}
.bnn-substep-title {{ font-weight: 700; font-size: 0.95rem; }}
.bnn-substep-detail {{ font-size: 0.8rem; opacity: 0.85; margin-top: 2px; }}

/* ===== Breadcrumbs ===== */
.bnn-crumbs {{
    display: flex; gap: 0.4rem; align-items: center;
    color: {_MUTED}; font-size: 0.85rem; margin-bottom: 0.4rem;
    flex-wrap: wrap;
}}
.bnn-crumbs .bnn-crumb-cur {{ color: #FFE3A8; font-weight: 700; }}
.bnn-crumbs .bnn-crumb-sep {{ opacity: 0.55; }}

/* ===== Feature card ===== */
.bnn-feat-card {{
    background: linear-gradient(180deg, rgba(42,24,16,0.85), rgba(26,17,8,0.85));
    border: 1px solid rgba(243,156,18,0.18);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    height: 100%;
}}
.bnn-feat-icon {{ font-size: 1.6rem; }}
.bnn-feat-title {{ font-weight: 800; font-size: 1.02rem; margin: 0.25rem 0 0.25rem; color: #FFE3A8; }}
.bnn-feat-desc  {{ font-size: 0.88rem; color: #DCC8A8; line-height: 1.5; }}
.bnn-feat-meta  {{ font-size: 0.75rem; color: {_MUTED}; margin-top: 0.55rem; }}

/* ===== Pills / badges ===== */
.bnn-pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    margin-left: 0.4rem;
    vertical-align: middle;
    letter-spacing: 0.02em;
}}
.bnn-pill-done    {{ background: rgba(39,174,96,0.18);  color: #84E29B; border: 1px solid rgba(39,174,96,0.35); }}
.bnn-pill-cur     {{ background: rgba(243,156,18,0.18); color: #FFE3A8; border: 1px solid rgba(243,156,18,0.35); }}
.bnn-pill-todo    {{ background: rgba(139,115,85,0.18); color: #BBA47D; border: 1px solid rgba(139,115,85,0.35); }}
.bnn-pill-locked  {{ background: rgba(255,255,255,0.04); color: {_MUTED}; border: 1px solid rgba(139,115,85,0.25); }}

/* ===== Sidebar tidy ===== */
section[data-testid="stSidebar"] .stExpander {{
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(139,115,85,0.2);
    border-radius: 10px;
}}

/* ===== Dialog buttons spacing ===== */
div[role="dialog"] .stButton > button {{ min-width: 7rem; }}
</style>"""


def inject_theme_css() -> None:
    """共通 CSS を毎描画で注入する。DOM は再描画ごとにリセットされるため毎回必要。"""
    st.markdown(_CSS, unsafe_allow_html=True)
