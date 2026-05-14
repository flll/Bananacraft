"""
ランタイム API キー解決（session / localStorage 同期値 > 環境変数）。

Streamlit の `st.session_state` から組み立てた辞書を `apply_context` で毎ラン登録する。
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional

_CONTEXT: Dict[str, str] = {}


def clear_context() -> None:
    global _CONTEXT
    _CONTEXT = {}


def apply_context(keys: Optional[Mapping[str, str]]) -> None:
    """空でない値だけをランタイムコンテキストに載せる。"""
    global _CONTEXT
    if not keys:
        _CONTEXT = {}
        return
    _CONTEXT = {k: v.strip() for k, v in keys.items() if isinstance(v, str) and v.strip()}


def get_from_context(name: str) -> Optional[str]:
    v = _CONTEXT.get(name, "").strip()
    return v or None


def resolve_env(primary: str, fallbacks: tuple[str, ...] = ()) -> str:
    """primary → fallbacks → OS 環境変数の順で最初に見つかった非空値を返す。"""
    for name in (primary,) + fallbacks:
        v = get_from_context(name) or os.getenv(name, "").strip()
        if v:
            return v
    raise ValueError(
        f"API キーが見つかりません: {primary}"
        + (f" または {', '.join(fallbacks)}" if fallbacks else "")
        + " をサイドバー・ブラウザ保存、または .env に設定してください。"
    )
