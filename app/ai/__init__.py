"""工程別 AI ルーティング（固定バインド）。外部からは routing を主に参照。"""
from .routing import AIStage, StageRoute, ROUTES, resolve_api_key, client_for_stage, text_model, image_model

__all__ = [
    "AIStage",
    "StageRoute",
    "ROUTES",
    "resolve_api_key",
    "client_for_stage",
    "text_model",
    "image_model",
]
