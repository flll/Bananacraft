"""
Bananacraft — 工程ごとの AI ルーティング（Google / OpenAI / Anthropic）

キー解決: key_store ランタイム > OS 環境変数。プロバイダごとに 1 本
（GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY）。OpenAI または
Anthropic のキーが無い工程は Gemini に切り替える。

BFCL（Function Calling 比較）: https://gorilla.cs.berkeley.edu/leaderboard.html
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Final, Literal, Optional, Tuple

from .key_store import resolve_env

ProviderName = Literal["google", "openai", "anthropic"]


class Provider(Enum):
    GOOGLE = auto()
    OPENAI = auto()
    ANTHROPIC = auto()


@dataclass(frozen=True)
class StageRoute:
    provider: Provider
    api_key_env: str
    model_id: str
    fallback_key_envs: Tuple[str, ...] = ()
    image_model_id: Optional[str] = None
    notes: str = ""


class AIStage(Enum):
    CONCEPT_BRAIN = auto()
    IMAGE_RENDER = auto()
    ZONING_PLAN = auto()
    ARCHITECT_VISION = auto()
    ARCHITECT_BUILD = auto()
    SEMANTIC_PASS = auto()
    INFRASTRUCTURE = auto()
    DECORATION = auto()


_GEM_TEXT = "gemini-3-pro-preview"
_GEM_IMG = "gemini-3-pro-image-preview"
_OAI_JSON = "gpt-5.5"
_OAI_VISION = "gpt-5.5"
_CLAUDE = "claude-sonnet-4-6"

# 既定: 精度寄りのマルチベンダー。キー欠落時は _gemini_only で上書き。
ROUTES: Final[dict[AIStage, StageRoute]] = {
    AIStage.CONCEPT_BRAIN: StageRoute(
        Provider.ANTHROPIC,
        "ANTHROPIC_API_KEY",
        _CLAUDE,
        (),
        notes="長文対話＋JSON 出力で Claude Sonnet 4.6 を既定。キー無し時は Gemini。",
    ),
    AIStage.IMAGE_RENDER: StageRoute(
        Provider.GOOGLE,
        "GEMINI_API_KEY",
        _GEM_TEXT,
        (),
        image_model_id=_GEM_IMG,
        notes="参照画像付き生成は Gemini 画像モデル。",
    ),
    AIStage.ZONING_PLAN: StageRoute(
        Provider.OPENAI,
        "OPENAI_API_KEY",
        _OAI_JSON,
        (),
        notes="BFCL 参考: https://gorilla.cs.berkeley.edu/leaderboard.html — 構造化 JSON で gpt-5.5。キー無し時は Gemini。",
    ),
    AIStage.ARCHITECT_VISION: StageRoute(
        Provider.OPENAI,
        "OPENAI_API_KEY",
        _OAI_VISION,
        (),
        notes="マルチモーダル解析に gpt-5.5。",
    ),
    AIStage.ARCHITECT_BUILD: StageRoute(
        Provider.OPENAI,
        "OPENAI_API_KEY",
        _OAI_JSON,
        (),
        notes="BFCL FC 系で gpt-5.5 を既定。",
    ),
    AIStage.SEMANTIC_PASS: StageRoute(
        Provider.GOOGLE,
        "GEMINI_API_KEY",
        _GEM_TEXT,
        (),
        notes="Mesh ボクセル上の窓・ドア・装飾を画像と照合して Gemini 3 Pro で JSON 化。",
    ),
    AIStage.INFRASTRUCTURE: StageRoute(
        Provider.OPENAI,
        "OPENAI_API_KEY",
        _OAI_JSON,
        (),
        notes="BFCL FC 系で gpt-5.5（建築 Stage2 と揃えて挙動差分を抑制）。",
    ),
    AIStage.DECORATION: StageRoute(
        Provider.ANTHROPIC,
        "ANTHROPIC_API_KEY",
        _CLAUDE,
        (),
        notes="画像＋tools: Claude Sonnet 4.6。BFCL 参考: https://gorilla.cs.berkeley.edu/leaderboard.html 。キー無し時は Gemini。",
    ),
}


def _gemini_route(stage: AIStage) -> StageRoute:
    """OpenAI/Anthropic キーが解決できないときの共通 Gemini ルート。"""
    img = ROUTES[AIStage.IMAGE_RENDER].image_model_id
    return StageRoute(
        Provider.GOOGLE,
        "GEMINI_API_KEY",
        _GEM_TEXT,
        (),
        image_model_id=img if stage == AIStage.IMAGE_RENDER else None,
        notes="fallback_gemini",
    )


def effective_route(stage: AIStage) -> StageRoute:
    """OpenAI/Anthropic のキーが解決できない工程は Gemini に落とす。"""
    base = ROUTES[stage]
    if base.provider == Provider.GOOGLE:
        return base

    if base.provider == Provider.OPENAI:
        openai_chain = tuple(
            dict.fromkeys(
                (base.api_key_env,)
                + tuple(x for x in base.fallback_key_envs if x.startswith("OPENAI_"))
            )
        )
        for n in openai_chain:
            try:
                resolve_env(n, ())
                return base
            except ValueError:
                continue
        return replace(_gemini_route(stage), model_id=_GEM_TEXT)

    if base.provider == Provider.ANTHROPIC:
        anthropic_chain = tuple(
            dict.fromkeys(
                (base.api_key_env,)
                + tuple(x for x in base.fallback_key_envs if x.startswith("ANTHROPIC_"))
            )
        )
        for n in anthropic_chain:
            try:
                resolve_env(n, ())
                return base
            except ValueError:
                continue
        return replace(_gemini_route(stage), model_id=_GEM_TEXT)

    return base


def resolve_api_key_for_stage(stage: AIStage) -> str:
    r = effective_route(stage)
    return resolve_env(r.api_key_env, r.fallback_key_envs)


def resolve_api_key(route: StageRoute) -> str:
    """互換: 明示的 StageRoute を渡す場合（provider に依らず route 内の env 列のみ使用）。"""
    return resolve_env(route.api_key_env, route.fallback_key_envs)


def text_model(stage: AIStage) -> str:
    return effective_route(stage).model_id


def image_model(stage: AIStage) -> str:
    r = effective_route(AIStage.IMAGE_RENDER)
    if not r.image_model_id:
        raise ValueError("IMAGE_RENDER に image_model_id がありません。")
    return r.image_model_id


def provider_name(p: Provider) -> ProviderName:
    return {Provider.GOOGLE: "google", Provider.OPENAI: "openai", Provider.ANTHROPIC: "anthropic"}[p]
