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

# Settings ページの Streamlit widget key ↔ TripoConfig フィールド名。
# ``style`` は selectbox 上 ``"None"`` 文字列 ↔ ``None`` の変換が必要。
TRIPO_WIDGET_FIELD_MAP: Dict[str, str] = {
    "bnn_tripo_mv": "model_version",
    "bnn_tripo_style": "style",
    "bnn_tripo_style_bs": "style_block_size",
    "bnn_tripo_gq": "geometry_quality",
    "bnn_tripo_face": "face_limit",
    "bnn_tripo_quad": "quad",
    "bnn_tripo_autosize": "auto_size",
    "bnn_tripo_tq": "texture_quality",
    "bnn_tripo_ta": "texture_alignment",
    "bnn_tripo_tex": "texture",
    "bnn_tripo_pbr": "pbr",
    "bnn_tripo_use_tex_model": "use_texture_model",
    "bnn_tripo_tex_mv": "texture_model_version",
    "bnn_tripo_tex_bake": "texture_bake",
    "bnn_tripo_vlo": "voxel_lower_bound",
    "bnn_tripo_vhi": "voxel_upper_bound",
    "bnn_tripo_mseed": "model_seed",
    "bnn_tripo_tseed": "texture_seed",
    "bnn_tripo_autofix": "enable_image_autofix",
}

TRIPO_RESET_BUTTON_KEY = "bnn_tripo_reset"
TRIPO_RESET_CONFIRMED_FLAG = f"_danger_confirmed_{TRIPO_RESET_BUTTON_KEY}"


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
    # ボクセル化時の解像度を `max(lower, min(upper, max(width, depth)))` で決める。
    # 1 voxel = 1 Minecraft ブロックなので、これが直接「建物のブロック数」に影響する。
    # 表面ブロック数の概算: ~6 × target_voxel² (表面のみのため)
    #   voxel_lower_bound=6  -> ~200 blocks (ドット絵スケール、推奨)
    #   voxel_lower_bound=12 -> ~800 blocks (中スケール)
    #   voxel_lower_bound=24 -> ~3500 blocks (大型詳細)
    voxel_lower_bound: int = 6
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

    @classmethod
    def defaults(cls) -> "TripoConfig":
        """リセット時に復帰する推奨値 (dataclass フィールド初期値と同一)。"""
        return cls()

    @staticmethod
    def style_to_widget(style: Optional[str]) -> str:
        """``TripoConfig.style`` → selectbox 用の ``"None"`` / スタイル名。"""
        return "None" if style is None else str(style)

    @staticmethod
    def style_from_widget(widget_value: str) -> Optional[str]:
        """selectbox の値 → ``TripoConfig.style``。"""
        if widget_value in (None, "None", "none", ""):
            return None
        return str(widget_value)

    def to_widget_state(self) -> Dict[str, Any]:
        """全 ``bnn_tripo_*`` widget key に書き込む値の dict を返す。"""
        out: Dict[str, Any] = {}
        for widget_key, field_name in TRIPO_WIDGET_FIELD_MAP.items():
            if field_name == "style":
                out[widget_key] = self.style_to_widget(self.style)
            else:
                out[widget_key] = getattr(self, field_name)
        return out

    def apply_widget_state(self, session_state: Any) -> None:
        """全 widget key を cfg 値で明示 SET (pop ではなく上書き)。

        Streamlit は key が session_state に残っていると ``value=`` を無視するため、
        リセット時は必ずこのメソッドで上書きする。
        """
        for widget_key, value in self.to_widget_state().items():
            session_state[widget_key] = value

    def ensure_widget_keys(self, session_state: Any) -> None:
        """欠けている widget key だけ cfg から seed する (初回表示用)。"""
        for widget_key, value in self.to_widget_state().items():
            if widget_key not in session_state:
                session_state[widget_key] = value

    @classmethod
    def from_widget_state(cls, session_state: Any) -> "TripoConfig":
        """session_state の widget key から TripoConfig を組み立てる。"""
        data: Dict[str, Any] = {}
        for widget_key, field_name in TRIPO_WIDGET_FIELD_MAP.items():
            if widget_key not in session_state:
                continue
            raw = session_state[widget_key]
            if field_name == "style":
                data[field_name] = cls.style_from_widget(str(raw))
            elif field_name in ("style_block_size", "face_limit", "model_seed", "texture_seed",
                                 "voxel_lower_bound", "voxel_upper_bound"):
                data[field_name] = int(raw)
            elif field_name in ("quad", "auto_size", "texture", "pbr", "use_texture_model",
                                "texture_bake", "enable_image_autofix"):
                data[field_name] = bool(raw)
            else:
                data[field_name] = raw
        base = cls.defaults()
        merged = {**base.to_dict(), **data}
        return cls.from_dict(merged)


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
        return TripoConfig.defaults()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return TripoConfig.defaults()
    if not isinstance(data, dict):
        return TripoConfig.defaults()
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
    return TripoConfig.defaults()


def tripo_reset_confirmed(session_state: Any) -> bool:
    """danger_button 確認後に立つフラグを消費して True を返す。"""
    return bool(session_state.pop(TRIPO_RESET_CONFIRMED_FLAG, False))
