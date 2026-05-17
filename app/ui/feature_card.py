"""機能訴求カード。ページ冒頭で「このページでできること」を 2〜3 枚並べる。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import streamlit as st


@dataclass
class FeatureCard:
    icon: str
    title: str
    description: str
    meta: Optional[str] = None  # 所要時間や API コスト目安


def render_feature_cards(cards: List[FeatureCard]) -> None:
    """与えられたカードを横並びで表示。"""
    if not cards:
        return
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        with col:
            meta_html = (
                f'<div class="bnn-feat-meta">{card.meta}</div>' if card.meta else ""
            )
            st.markdown(
                f"""
<div class="bnn-feat-card">
  <div class="bnn-feat-icon">{card.icon}</div>
  <div class="bnn-feat-title">{card.title}</div>
  <div class="bnn-feat-desc">{card.description}</div>
  {meta_html}
</div>
                """,
                unsafe_allow_html=True,
            )
