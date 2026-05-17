"""上部の常設横ステッパー & 縦サブステッパー。

メインフロー（4 段）:
    setup -> concept -> city_plan -> building

各ページ冒頭で `render_top_stepper("city_plan", completed={...})` を呼ぶ。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional

import streamlit as st


# ---- Top stepper -------------------------------------------------------

_MAIN_STEPS: List[tuple[str, str, str]] = [
    # (key, label, emoji)
    ("setup",     "Setup",     "🛠️"),
    ("concept",   "Concept",   "💡"),
    ("city_plan", "City Plan", "🗺️"),
    ("building",  "Building",  "🏛️"),
]


def render_top_stepper(
    current: str,
    completed: Optional[Iterable[str]] = None,
) -> None:
    """画面上部に 4 段の横ステッパーを描く。

    Args:
        current: 現在のステップキー
        completed: 完了済みステップキー集合
    """
    done = set(completed or [])
    parts: List[str] = ['<div class="bnn-stepper">']
    for idx, (key, label, emoji) in enumerate(_MAIN_STEPS, start=1):
        cls = "bnn-step"
        if key in done:
            cls += " is-done"
        if key == current:
            cls += " is-cur"
        symbol = "✓" if (key in done and key != current) else str(idx)
        parts.append(
            f'<div class="{cls}">'
            f'  <span class="bnn-step-num">{symbol}</span>'
            f'  <span>{emoji} {label}</span>'
            f'</div>'
        )
    parts.append("</div>")
    st.markdown("\n".join(parts), unsafe_allow_html=True)


# ---- Vertical sub-stepper ---------------------------------------------

@dataclass
class SubStep:
    """縦サブステッパーの 1 段."""
    key: str
    title: str
    detail: str = ""
    state: str = "todo"   # "done" | "cur" | "todo" | "locked"


def render_substepper(steps: List[SubStep]) -> None:
    """個別 Building ページ用の縦サブステッパー。"""
    parts: List[str] = []
    for s in steps:
        cls = "bnn-substep"
        emoji = "◯"
        if s.state == "done":
            cls += " is-done"; emoji = "✓"
        elif s.state == "cur":
            cls += " is-cur"; emoji = "◉"
        elif s.state == "locked":
            cls += " is-locked"; emoji = "🔒"
        parts.append(
            f'<div class="{cls}">'
            f'  <div style="font-size:1rem;line-height:1.4;">{emoji}</div>'
            f'  <div>'
            f'    <div class="bnn-substep-title">{s.title}</div>'
            f'    {("<div class=\"bnn-substep-detail\">" + s.detail + "</div>") if s.detail else ""}'
            f'  </div>'
            f'</div>'
        )
    st.markdown("\n".join(parts), unsafe_allow_html=True)


# ---- Step state derivation --------------------------------------------

def derive_main_steps_state(
    *,
    has_project: bool,
    has_concept: bool,
    has_zoning: bool,
    has_blueprint_for_selected: bool,
) -> dict:
    """現状の session_state からメインフローの (current, completed) を推定。"""
    completed: List[str] = []
    if has_project:
        completed.append("setup")
    if has_concept:
        completed.append("concept")
    if has_zoning:
        completed.append("city_plan")
    if has_blueprint_for_selected:
        completed.append("building")

    # current = 最初に未完了のステップ
    current = "setup"
    for key, *_ in _MAIN_STEPS:
        if key not in completed:
            current = key
            break
    else:
        current = "building"
    return {"current": current, "completed": completed}
