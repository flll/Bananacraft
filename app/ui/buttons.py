"""ボタンの 3 階層 (primary / secondary / danger) を統一する薄いラッパー。

Streamlit 標準の `kind="primary"` を活かしつつ、Danger は `st.dialog`
で確認ステップを必ず踏ませる。
"""
from __future__ import annotations

from typing import Callable, Optional

import streamlit as st


def primary_button(
    label: str,
    *,
    key: Optional[str] = None,
    help: Optional[str] = None,
    disabled: bool = False,
    use_container_width: bool = False,
) -> bool:
    """次のステップに進むメインボタン。"""
    return st.button(
        label,
        key=key,
        help=help,
        disabled=disabled,
        type="primary",
        use_container_width=use_container_width,
    )


def secondary_button(
    label: str,
    *,
    key: Optional[str] = None,
    help: Optional[str] = None,
    disabled: bool = False,
    use_container_width: bool = False,
) -> bool:
    """途中処理（再生成、View など）。アウトライン表示。"""
    return st.button(
        label,
        key=key,
        help=help,
        disabled=disabled,
        type="secondary",
        use_container_width=use_container_width,
    )


def danger_button(
    label: str,
    *,
    key: str,
    confirm_title: str = "本当によろしいですか？",
    confirm_body: str = "この操作は元に戻せません。",
    confirm_label: str = "はい、実行する",
    cancel_label: str = "キャンセル",
    help: Optional[str] = None,
    on_confirm: Optional[Callable[[], None]] = None,
    disabled: bool = False,
    use_container_width: bool = False,
) -> bool:
    """破壊的操作。クリック → 確認ダイアログを経て初めて True を返す。

    `on_confirm` を渡せばダイアログ内で呼ばれる（rerun は呼び出し側で）。
    返り値 True は「確認 OK が押された」状態のフラグとして使える。
    """
    clicked = st.button(
        label,
        key=key,
        help=help,
        disabled=disabled,
        type="secondary",
        use_container_width=use_container_width,
    )
    if clicked:
        st.session_state[f"_danger_pending_{key}"] = True

    pending = st.session_state.get(f"_danger_pending_{key}", False)
    confirmed = False
    if pending:
        @st.dialog(confirm_title)  # type: ignore[misc]
        def _confirm_dialog() -> None:
            st.warning(confirm_body, icon="⚠️")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(cancel_label, key=f"{key}_cancel", use_container_width=True):
                    st.session_state[f"_danger_pending_{key}"] = False
                    st.rerun()
            with c2:
                if st.button(
                    confirm_label,
                    key=f"{key}_ok",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state[f"_danger_pending_{key}"] = False
                    st.session_state[f"_danger_confirmed_{key}"] = True
                    if on_confirm is not None:
                        on_confirm()
                    st.rerun()

        _confirm_dialog()

    if st.session_state.pop(f"_danger_confirmed_{key}", False):
        confirmed = True
    return confirmed
