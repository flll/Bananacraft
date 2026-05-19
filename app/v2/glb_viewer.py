"""Tripo3D が生成した GLB を `<model-viewer>` Web Component で表示する。

外部 pip 依存なし: `<script type="module">` で unpkg から model-viewer を読み込み、
GLB バイナリは base64 で HTML に埋め込んで Streamlit から配信する手間を省く。
"""
from __future__ import annotations

import base64
import os
from typing import Optional

import streamlit as st


def _embed_model_viewer(
    data: bytes,
    *,
    height: int,
    bg_color: str,
    auto_rotate: bool,
    alt: str,
) -> bool:
    """GLB bytes を `<model-viewer>` として埋め込む内部実装。"""
    b64 = base64.b64encode(data).decode("ascii")
    rotate_attr = "auto-rotate" if auto_rotate else ""

    html = f"""
<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
<style>
    .bnn-glb-host {{
        width: 100%;
        height: {height}px;
        background: {bg_color};
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0,0,0,0.35);
    }}
    .bnn-glb-host model-viewer {{
        width: 100%;
        height: 100%;
        --poster-color: transparent;
    }}
</style>
<div class="bnn-glb-host">
  <model-viewer
    src="data:model/gltf-binary;base64,{b64}"
    alt="{alt}"
    camera-controls
    {rotate_attr}
    shadow-intensity="1.1"
    exposure="1.1"
    interaction-prompt="auto"
    interaction-prompt-style="basic"
    environment-image="neutral"
    style="background-color: {bg_color};"
  ></model-viewer>
</div>
"""
    try:
        st.components.v1.html(html, height=height + 20)
    except Exception as e:
        st.warning(f"GLB ビューア埋め込みに失敗: {e}")
        return False
    return True


def render_glb(
    glb_path: str,
    *,
    height: int = 520,
    bg_color: str = "#1A1108",
    auto_rotate: bool = True,
) -> bool:
    """GLB ファイルを `<model-viewer>` で埋め込み表示する。

    Returns:
        正常に埋め込めた場合 True、ファイルが無い・読み込み失敗で False。
    """
    if not glb_path or not os.path.isfile(glb_path):
        st.info("GLB ファイルが見つかりません。", icon="📦")
        return False

    try:
        with open(glb_path, "rb") as f:
            data = f.read()
    except OSError as e:
        st.warning(f"GLB の読み込みに失敗: {e}")
        return False

    ok = _embed_model_viewer(
        data,
        height=height,
        bg_color=bg_color,
        auto_rotate=auto_rotate,
        alt="Tripo3D mesh preview",
    )
    if not ok:
        return False

    size_kb = len(data) / 1024
    st.caption(
        f"📦 {os.path.basename(glb_path)} — {size_kb:,.1f} KB ／ ドラッグで回転・スクロールでズーム"
    )
    return True


def render_glb_bytes(
    data: bytes,
    *,
    height: int = 520,
    bg_color: str = "#1A1108",
    auto_rotate: bool = False,
    caption: Optional[str] = None,
    alt: str = "Voxel preview",
) -> bool:
    """GLB バイナリを直接 `<model-viewer>` で表示する。

    一時ファイルを作らずに `data:model/gltf-binary;base64,...` で埋め込むため、
    Streamlit re-run のたびに新しい GLB を渡しても余分な I/O が発生しない。

    Returns:
        正常に埋め込めた場合 True、データが空 / マジック不一致で False。
    """
    if not data:
        st.info("GLB データが空です。", icon="📦")
        return False
    if len(data) < 4 or data[:4] != b"glTF":
        st.warning("GLB マジックバイト (`glTF`) が一致しません。")
        return False

    ok = _embed_model_viewer(
        data,
        height=height,
        bg_color=bg_color,
        auto_rotate=auto_rotate,
        alt=alt,
    )
    if not ok:
        return False

    if caption:
        st.caption(caption)
    else:
        st.caption(f"📦 {len(data) / 1024:,.1f} KB ／ ドラッグで回転・スクロールでズーム")
    return True


def find_glb_in_dir(project_dir: str, zone_id: int) -> Optional[str]:
    """`mesh_{zone_id}.glb` を探して返す。"""
    import glob as _glob

    paths = sorted(_glob.glob(os.path.join(project_dir, f"mesh_{zone_id}.*")))
    for p in paths:
        if p.lower().endswith(".glb") and os.path.isfile(p):
            return p
    return None
