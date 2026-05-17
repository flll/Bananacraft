"""ブレッドクラム。Project > City Plan > Building: name > Build のような階層表示。"""
from __future__ import annotations

from typing import List, Tuple

import streamlit as st


def render_breadcrumbs(crumbs: List[Tuple[str, bool]]) -> None:
    """ブレッドクラムを描画。

    Args:
        crumbs: [(label, is_current), ...]。is_current=True のものは強調表示。
    """
    parts: List[str] = ['<div class="bnn-crumbs">']
    last = len(crumbs) - 1
    for i, (label, is_cur) in enumerate(crumbs):
        cls = "bnn-crumb-cur" if is_cur else "bnn-crumb"
        parts.append(f'<span class="{cls}">{label}</span>')
        if i < last:
            parts.append('<span class="bnn-crumb-sep">›</span>')
    parts.append("</div>")
    st.markdown("\n".join(parts), unsafe_allow_html=True)
