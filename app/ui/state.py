"""ページ横断の session_state アクセサ。

新ナビゲーション (`st.navigation`) では各ページ関数の実行スコープが
変わるため、`st.session_state` への out-of-band な書き込み/読み出しは
このモジュール経由に統一する。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import streamlit as st


# ---- Initialization ---------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    # コア (Phase 0 で確立)
    "project_name": "",
    "file_manager": None,
    "gemini_client": None,
    "chat_session": None,
    "architect": None,
    "carpenter_session": None,
    # ナビゲーション
    "selected_building": None,   # Phase 1B のカードから選んだ建物 dict
    # コンセプト & 都市計画
    "concept": None,
    "zoning": None,
    # 建物デザイン
    "design_images": None,       # {decorated, structure}
    "decoration_status": None,
    # API キー & その他
    "api_key_context": {},
    "_browser_keys_hydrated": False,
    "password_correct": False,
}


def ensure_session_defaults() -> None:
    for k, v in _DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---- Convenience accessors -------------------------------------------

def has_project() -> bool:
    return bool(st.session_state.get("project_name"))


def has_concept() -> bool:
    fm = st.session_state.get("file_manager")
    if not fm:
        return False
    return fm.exists("concept_art.jpg")


def has_zoning() -> bool:
    fm = st.session_state.get("file_manager")
    if not fm:
        return False
    return fm.exists("zoning_adjusted.json") or fm.exists("zoning_data.json")


def has_blueprint_for_selected() -> bool:
    fm = st.session_state.get("file_manager")
    b = st.session_state.get("selected_building")
    if not fm or not b:
        return False
    return fm.exists(f"building_{b['id']}_blocks_v2.json")


def has_decoration_for_selected() -> bool:
    fm = st.session_state.get("file_manager")
    b = st.session_state.get("selected_building")
    if not fm or not b:
        return False
    return fm.exists(f"building_{b['id']}_decoration.json")


def get_zoning_buildings() -> List[dict]:
    """`zoning` から建物 dict のリストを取り出す（adjusted / legacy 両対応）。"""
    z = st.session_state.get("zoning")
    if z is None:
        return []
    if isinstance(z, dict):
        return list(z.get("buildings", []))
    if isinstance(z, list):
        return list(z)
    return []


def refresh_selected_from_zoning() -> None:
    """zoning_adjusted で建物座標が変わった場合に selected_building を更新する。"""
    sel = st.session_state.get("selected_building")
    if not sel:
        return
    for b in get_zoning_buildings():
        if b.get("id") == sel.get("id"):
            st.session_state["selected_building"] = b
            return


def project_origin() -> tuple:
    fm = st.session_state.get("file_manager")
    if fm and fm.exists("project_config.json"):
        cfg = fm.load_json("project_config.json") or {}
        o = cfg.get("origin", {"x": 0, "y": 64, "z": 0})
        return (int(o.get("x", 0)), int(o.get("y", 64)), int(o.get("z", 0)))
    return (0, 64, 0)


def save_project_origin(x: int, y: int, z: int) -> None:
    fm = st.session_state.get("file_manager")
    if not fm:
        return
    cfg: Dict[str, Any] = {}
    if fm.exists("project_config.json"):
        cfg = fm.load_json("project_config.json") or {}
    cfg["origin"] = {"x": int(x), "y": int(y), "z": int(z)}
    fm.save_json("project_config.json", cfg)


def reset_project() -> None:
    """`Restart Project` / `プロジェクトを閉じる` 用。"""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    ensure_session_defaults()


# ---- API key hydration -----------------------------------------------

def hydrate_api_keys_from_browser() -> None:
    """初回のみ localStorage から API キーを読んで session_state に書き戻す。"""
    if st.session_state.get("_browser_keys_hydrated"):
        return
    try:
        from ai.browser_keys import load_persisted_keys
    except ImportError:  # pragma: no cover
        st.session_state["_browser_keys_hydrated"] = True
        return
    persisted = load_persisted_keys()
    if persisted:
        ctx = dict(st.session_state.get("api_key_context") or {})
        ctx.update(persisted)
        st.session_state["api_key_context"] = ctx
    st.session_state["_browser_keys_hydrated"] = True


def apply_api_keys_to_env() -> None:
    """`api_key_context` の中身を `os.environ` と key_store に反映。"""
    try:
        from ai.key_store import apply_context
    except ImportError:  # pragma: no cover
        return
    ctx = st.session_state.get("api_key_context") or {}
    apply_context(ctx)
    for k, v in ctx.items():
        if isinstance(v, str) and v.strip():
            os.environ[k] = v.strip()
