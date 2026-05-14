"""
ブラウザ localStorage への API キー永続化（streamlit-js-eval）。

XSS があるとキーが漏洩しうるため README で警告する。
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional

LS_KEY = "bananacraft_api_keys_v1"


def load_persisted_keys() -> Dict[str, str]:
    """localStorage から JSON 辞書を読む。失敗時は空。"""
    try:
        from streamlit_js_eval import streamlit_js_eval
    except ImportError:
        return {}
    try:
        b64: Optional[str] = streamlit_js_eval(
            js_expressions=(
                "(() => { const s = localStorage.getItem('bananacraft_api_keys_v1'); "
                "if(!s) return ''; return btoa(unescape(encodeURIComponent(s))); })()"
            ),
            want_output=True,
        )
        if not b64:
            return {}
        raw = base64.b64decode(b64).decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        return {}
    return {}


def save_persisted_keys(keys: Dict[str, Any]) -> None:
    """localStorage に JSON を保存。"""
    try:
        from streamlit_js_eval import streamlit_js_eval
    except ImportError:
        raise RuntimeError("streamlit-js-eval がインストールされていません。")
    clean = {k: v for k, v in keys.items() if isinstance(v, str) and v.strip()}
    payload = base64.b64encode(json.dumps(clean, ensure_ascii=False).encode("utf-8")).decode("ascii")
    streamlit_js_eval(
        js_expressions=(
            f"localStorage.setItem('{LS_KEY}', "
            f"decodeURIComponent(escape(atob('{payload}'))))"
        ),
        want_output=False,
    )


def clear_persisted_keys() -> None:
    try:
        from streamlit_js_eval import streamlit_js_eval
        streamlit_js_eval(js_expressions=f"localStorage.removeItem('{LS_KEY}')", want_output=False)
    except ImportError:
        pass
