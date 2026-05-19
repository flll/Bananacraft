"""Streamlit 側からの mc_assets バックグラウンド DL コントローラ。

- `@st.cache_resource` で 1 回だけスレッドを起動
- 進捗は `_STATE` (プロセス共通の dict) と `st.session_state["mc_assets_status"]`
  にミラー書き
- Settings から再ダウンロードする時は `restart()` を呼ぶ

ステージは ``pending`` → ``manifest`` → ``download`` → ``downloaded`` →
``extract`` → ``ready`` (成功) / ``failed`` (失敗) / ``disabled`` (強制 procedural)
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from v2 import mc_assets


logger = logging.getLogger(__name__)


_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {
    "stage": "pending",
    "message": "",
    "version": None,
    "jar_path": None,
    "blocks_dir": None,
    "texture_count": 0,
    "updated_at": 0.0,
    "force_procedural": False,
}


def _set_state(**kw: Any) -> None:
    with _LOCK:
        _STATE.update(kw)
        _STATE["updated_at"] = time.time()


def get_state() -> Dict[str, Any]:
    """現在のステータスのスナップショットを返す (UI 用)。"""
    with _LOCK:
        return dict(_STATE)


def _on_progress(stage: str, message: str) -> None:
    logger.info("[mc_assets] %s: %s", stage, message)
    _set_state(stage=stage, message=message)


def _run() -> Optional[Dict[str, Any]]:
    """ensure_official_assets を 1 回実行し、最終結果を返す。"""
    _set_state(stage="manifest", message="connecting to Mojang piston-meta...")
    result = mc_assets.ensure_official_assets(on_progress=_on_progress)
    if not result:
        _set_state(
            stage="failed",
            message="jar の取得に失敗しました。手作りアトラスで継続します。",
        )
        return None

    version = result["version"]
    textures = result["textures"]
    try:
        removed = mc_assets.prune_other_versions(version)
        if removed:
            logger.info("pruned %d old jar caches", removed)
    except Exception:  # noqa: BLE001
        logger.warning("prune_other_versions failed", exc_info=True)

    _set_state(
        stage="ready",
        message=f"{len(textures)} textures ready",
        version=version,
        jar_path=str(result["jar_path"]),
        blocks_dir=str(result["blocks_dir"]),
        texture_count=int(len(textures)),
    )
    return result


@st.cache_resource(show_spinner=False)
def _ensure_started() -> Dict[str, Any]:
    """初回呼び出し時にバックグラウンドスレッドを 1 度だけ起動する。"""

    def _worker() -> None:
        try:
            _run()
        except Exception:  # noqa: BLE001
            logger.exception("mc_assets background thread crashed")
            _set_state(stage="failed", message="internal error")

    thread = threading.Thread(
        target=_worker, name="bnn-mc-assets", daemon=True
    )
    thread.start()
    return {"thread": thread, "started_at": time.time()}


def kickoff() -> None:
    """起動時に 1 度だけ呼ぶ。session_state にも現状を反映する。"""
    if _STATE.get("force_procedural"):
        _set_state(stage="disabled", message="手作りアトラス固定モード")
    else:
        _ensure_started()
    st.session_state["mc_assets_status"] = get_state()


def restart() -> None:
    """キャッシュをクリアしてスレッドを再起動。"""
    _ensure_started.clear()
    _set_state(
        stage="pending",
        message="再ダウンロードを開始します...",
        version=None,
        jar_path=None,
        blocks_dir=None,
        texture_count=0,
    )
    if not _STATE.get("force_procedural"):
        _ensure_started()
    st.session_state["mc_assets_status"] = get_state()


def clear_jar_cache() -> int:
    """`~/.cache/bananacraft/mc/` を丸ごと削除。削除したエントリ数を返す。"""
    root = mc_assets.DEFAULT_CACHE_ROOT
    if not root.exists():
        return 0
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        except OSError:
            logger.warning("failed to remove %s", child, exc_info=True)
    return removed


def set_force_procedural(value: bool) -> None:
    """True にすると jar DL を抑止し、手作りアトラスのみを使う。"""
    _set_state(force_procedural=bool(value))
    if value:
        _set_state(stage="disabled", message="手作りアトラス固定モード")
    st.session_state["mc_assets_status"] = get_state()


def is_force_procedural() -> bool:
    return bool(_STATE.get("force_procedural"))


def atlas_version_tag() -> str:
    """`@st.cache_data` のキー用に「現在使えるアトラスのバージョン文字列」を返す。

    - jar 取得済み: ``official:<version>``
    - 取得失敗 / 取得前 / 強制 procedural: ``procedural``
    """
    if _STATE.get("force_procedural"):
        return "procedural"
    if _STATE.get("stage") == "ready" and _STATE.get("version"):
        return f"official:{_STATE['version']}"
    return "procedural"


__all__ = [
    "kickoff",
    "restart",
    "get_state",
    "clear_jar_cache",
    "set_force_procedural",
    "is_force_procedural",
    "atlas_version_tag",
]
