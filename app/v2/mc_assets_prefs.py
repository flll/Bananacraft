"""mc_assets まわりのユーザー設定 (永続化)。

`tripo_config.json` と並んで `mc_assets_prefs.json` をユーザー設定ディレクトリに置く。
今は `force_procedural` フラグのみだが、将来 channel (release / snapshot) や
カスタム version pin もここに追加できる。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict


@dataclass
class McAssetsPrefs:
    """Minecraft アセット取得まわりの永続設定。"""

    force_procedural: bool = False


def _path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return Path(base) / "bananacraft" / "mc_assets_prefs.json"


def load() -> McAssetsPrefs:
    p = _path()
    if not p.is_file():
        return McAssetsPrefs()
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return McAssetsPrefs()
    if not isinstance(raw, dict):
        return McAssetsPrefs()
    valid = {f.name for f in fields(McAssetsPrefs)}
    filtered: Dict[str, Any] = {k: v for k, v in raw.items() if k in valid}
    return McAssetsPrefs(**filtered)


def save(prefs: McAssetsPrefs) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(asdict(prefs), f, ensure_ascii=False, indent=2)


__all__ = ["McAssetsPrefs", "load", "save"]
