"""
Bananacraft — 工程ごとの固定 AI ルーティング

精度優先のため、各工程に「専用の API キー環境変数」と「モデル ID」を割り当てる。
キーが未設定の場合は GEMINI_API_KEY にフォールバックする（既存デプロイ互換）。

モデル・キー名は製品方針としてコード上で固定（運用で頻繁に切り替えない前提）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final, Optional

from google import genai


@dataclass(frozen=True)
class StageRoute:
    """1 工程分のバインド。"""

    api_key_env: str
    """この工程で最初に参照する API キー環境変数。"""
    model_id: str
    """テキスト・マルチモーダル・Function Calling 用モデル。"""
    fallback_key_envs: tuple[str, ...] = ("GEMINI_API_KEY",)
    image_model_id: Optional[str] = None
    """画像生成のみ別モデルにしたい場合。None のときは model_id を流用しない（画像 API 専用で必須）。"""


class AIStage(Enum):
    CONCEPT_BRAIN = auto()
    """コンセプト対話・プロンプト推敲（チャット JSON）。"""
    IMAGE_RENDER = auto()
    """コンセプト／設計用の画像生成（Nano Banana Pro 系）。"""
    ZONING_PLAN = auto()
    """200x200 区画 JSON（チャット履歴に依存しない単発生成）。"""
    ARCHITECT_VISION = auto()
    """躯体画像 → 構造記述（Stage 1）。"""
    ARCHITECT_BUILD = auto()
    """構造記述 → 建築ツール FC（Stage 2）。"""
    INFRASTRUCTURE = auto()
    """道路・広場などインフラ FC。"""
    DECORATION = auto()
    """外装装飾 FC。"""


# --- 製品固定: 強モデル前提（必要に応じてモデル ID のみ将来更新） ---
_GEMINI_TEXT = "gemini-3-pro-preview"
_GEMINI_IMAGE = "gemini-3-pro-image-preview"

ROUTES: Final[dict[AIStage, StageRoute]] = {
    AIStage.CONCEPT_BRAIN: StageRoute(
        api_key_env="GEMINI_API_KEY_CONCEPT",
        model_id=_GEMINI_TEXT,
    ),
    AIStage.IMAGE_RENDER: StageRoute(
        api_key_env="GEMINI_API_KEY_IMAGE",
        model_id=_GEMINI_TEXT,
        image_model_id=_GEMINI_IMAGE,
    ),
    AIStage.ZONING_PLAN: StageRoute(
        api_key_env="GEMINI_API_KEY_ZONING",
        model_id=_GEMINI_TEXT,
    ),
    AIStage.ARCHITECT_VISION: StageRoute(
        api_key_env="GEMINI_API_KEY_ARCHITECT_VISION",
        model_id=_GEMINI_TEXT,
    ),
    AIStage.ARCHITECT_BUILD: StageRoute(
        api_key_env="GEMINI_API_KEY_ARCHITECT_BUILD",
        model_id=_GEMINI_TEXT,
    ),
    AIStage.INFRASTRUCTURE: StageRoute(
        api_key_env="GEMINI_API_KEY_INFRA",
        model_id=_GEMINI_TEXT,
    ),
    AIStage.DECORATION: StageRoute(
        api_key_env="GEMINI_API_KEY_DECORATOR",
        model_id=_GEMINI_TEXT,
    ),
}


def resolve_api_key(route: StageRoute) -> str:
    for name in (route.api_key_env, *route.fallback_key_envs):
        val = os.getenv(name, "").strip()
        if val:
            return val
    raise ValueError(
        f"API キーが見つかりません。{route.api_key_env} または "
        f"{', '.join(route.fallback_key_envs)} を .env に設定してください。"
    )


def text_model(stage: AIStage) -> str:
    return ROUTES[stage].model_id


def image_model(stage: AIStage) -> str:
    r = ROUTES[stage]
    if not r.image_model_id:
        raise ValueError(f"Stage {stage} に image_model_id が定義されていません。")
    return r.image_model_id


def client_for_stage(stage: AIStage, api_key_override: Optional[str] = None) -> genai.Client:
    """工程に応じた GenAI クライアント。override 時は全工程共通キーとして扱う（プレビュー用）。"""
    if api_key_override:
        return genai.Client(api_key=api_key_override)
    return genai.Client(api_key=resolve_api_key(ROUTES[stage]))


def client_for_route(route: StageRoute, api_key_override: Optional[str] = None) -> genai.Client:
    if api_key_override:
        return genai.Client(api_key=api_key_override)
    return genai.Client(api_key=resolve_api_key(route))
