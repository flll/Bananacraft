"""Tripo3D 設定の dataclass と JSON 永続化。

Settings ページで編集された値を `~/.config/bananacraft/tripo_config.json` に保存し、
次回起動時にロードする。`MeshArchitect.build_from_image` には dataclass 形式で渡す。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---- 選択肢定数 -------------------------------------------------------

# Tripo3D model version の代表値。新バージョンが出たら拡張する。
MODEL_VERSION_CHOICES: List[str] = [
    "v2.5-20250123",
    "v2.0-20240919",
    "v1.4-20240625",
]

# Tripo3D の post-process スタイル (stylize_model タスク)。
# image_to_model 完了後に別タスクとして適用する。
# None は適用しない (= ベースメッシュをそのまま使う)。
# 公式 PostStyle enum: lego / voxel / voronoi / minecraft
STYLE_CHOICES: List[str] = ["None", "minecraft", "voxel", "lego", "voronoi"]

QUALITY_CHOICES: List[str] = ["standard", "detailed"]
TEXTURE_ALIGNMENT_CHOICES: List[str] = ["original_image", "geometry"]

# Texture model (後段テクスチャ精製) のバージョン。
# v3.0-20250812: 最新の高品質モデル。
# v2.5-20250123: 旧版。互換性確認用。
TEXTURE_MODEL_VERSION_CHOICES: List[str] = ["v3.0-20250812", "v2.5-20250123"]


# ---- TripoConfig dataclass --------------------------------------------


@dataclass
class TripoConfig:
    """Tripo3D の image_to_model タスクに渡す設定をまとめた dataclass。"""

    # --- Model 設定 ----------------------------------------------------
    model_version: str = "v2.5-20250123"
    # 後処理スタイル (stylize_model タスク)。image_to_model の後段で別タスクとして
    # 適用される。"minecraft" を選ぶと Tripo 側で Minecraft ブロック風メッシュに
    # 変換してから Bananacraft がボクセル化する。None なら後段スタイル無し。
    style: Optional[str] = "minecraft"
    # stylize_model の block_size。小さいほど粒度が細かい (= 詳細だがブロック多い)。
    style_block_size: int = 80

    # --- Geometry 設定 -------------------------------------------------
    geometry_quality: str = "standard"
    face_limit: int = 30000
    quad: bool = False
    auto_size: bool = False

    # --- Texture 設定 --------------------------------------------------
    texture_quality: str = "detailed"
    texture_alignment: str = "original_image"
    texture: bool = True
    pbr: bool = True

    # --- Seed / 補助 ---------------------------------------------------
    model_seed: int = 42
    texture_seed: int = 42
    enable_image_autofix: bool = False

    # --- Texture Model (後段テクスチャ精製) -----------------------------
    # image_to_model で生成したベースメッシュに対して、texture_model タスクを
    # 追加で実行して高品質テクスチャを焼き直す。クレジット追加消費 + 時間増。
    use_texture_model: bool = False
    texture_model_version: str = "v3.0-20250812"
    texture_bake: bool = True

    # --- ボクセル解像度 (このリポ内部用、Tripo API には送らない) ----------
    voxel_lower_bound: int = 12
    voxel_upper_bound: int = 48

    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TripoConfig":
        valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in (d or {}).items() if k in valid}
        # style が "None" 文字列で来た場合は None に正規化
        if filtered.get("style") in (None, "None", "none", ""):
            filtered["style"] = None
        return cls(**filtered)

    def to_tripo_kwargs(self) -> Dict[str, Any]:
        """`TripoClient.create_image_task(**kwargs)` 用に展開した dict を返す。

        post-process スタイル (`style`) はこのタスクでは受け付けられないので含めない。
        スタイル適用は `to_stylize_kwargs` で別タスクとして実行する。
        """
        return {
            "model_version": self.model_version,
            "face_limit": int(self.face_limit),
            "texture": bool(self.texture),
            "pbr": bool(self.pbr),
            "texture_quality": self.texture_quality,
            "geometry_quality": self.geometry_quality,
            "texture_alignment": self.texture_alignment,
            "auto_size": bool(self.auto_size),
            "quad": bool(self.quad),
            "model_seed": int(self.model_seed) if self.model_seed is not None else None,
            "texture_seed": int(self.texture_seed) if self.texture_seed is not None else None,
            "enable_image_autofix": bool(self.enable_image_autofix),
        }

    def to_stylize_kwargs(self) -> Optional[Dict[str, Any]]:
        """`TripoClient.create_stylize_task(**kwargs)` 用に展開した dict を返す。

        `style` が未設定 (None) の場合は None を返す。
        `original_model_task_id` は呼び出し側で渡す。
        """
        if not self.style:
            return None
        return {
            "style": self.style,
            "block_size": int(self.style_block_size),
        }

    def to_texture_kwargs(self) -> Dict[str, Any]:
        """`TripoClient.create_texture_task(**kwargs)` 用に展開した dict を返す。

        `original_model_task_id` と `image_path` (または `text_prompt`) は呼び出し側で渡す。
        """
        return {
            "model_version": self.texture_model_version,
            "texture": bool(self.texture),
            "pbr": bool(self.pbr),
            "texture_quality": self.texture_quality,
            "texture_alignment": self.texture_alignment,
            "texture_seed": int(self.texture_seed) if self.texture_seed is not None else None,
            "bake": bool(self.texture_bake),
        }


# ---- 永続化 -----------------------------------------------------------


def _config_path() -> Path:
    """`$XDG_CONFIG_HOME/bananacraft/tripo_config.json` または `~/.config/...`."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return Path(base) / "bananacraft" / "tripo_config.json"


def load_tripo_config() -> TripoConfig:
    """ディスクから読み込む。無ければデフォルト値で返す。"""
    p = _config_path()
    if not p.is_file():
        return TripoConfig()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return TripoConfig()
    if not isinstance(data, dict):
        return TripoConfig()
    return TripoConfig.from_dict(data)


def save_tripo_config(cfg: TripoConfig) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.to_dict()
    # JSON に書く際、style=None は文字列 "None" に正規化しない (load 側で吸収)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def reset_tripo_config() -> TripoConfig:
    """ディスクファイルを削除し、デフォルト値の TripoConfig を返す。"""
    p = _config_path()
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass
    return TripoConfig()
