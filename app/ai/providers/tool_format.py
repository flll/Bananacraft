"""Gemini / OpenAI / Anthropic 向けにツール宣言 JSON を正規化。"""
from __future__ import annotations

from typing import Any, Dict, List, Union

Json = Dict[str, Any]


def _norm_type(t: Union[str, None]) -> str:
    if t is None:
        return "string"
    m = {
        "OBJECT": "object",
        "ARRAY": "array",
        "INTEGER": "integer",
        "NUMBER": "number",
        "BOOLEAN": "boolean",
        "STRING": "string",
    }
    return m.get(str(t).upper(), str(t).lower())


def normalize_json_schema(schema: Any) -> Any:
    """OpenAI / Anthropic が期待する JSON Schema 風に揃える（再帰）。"""
    if isinstance(schema, list):
        return [normalize_json_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out: Dict[str, Any] = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            out[k] = _norm_type(v)
        elif k in ("properties", "patternProperties") and isinstance(v, dict):
            out[k] = {kk: normalize_json_schema(vv) for kk, vv in v.items()}
        elif k == "items":
            out[k] = normalize_json_schema(v)
        elif k in ("anyOf", "oneOf", "allOf") and isinstance(v, list):
            out[k] = [normalize_json_schema(x) for x in v]
        elif isinstance(v, dict):
            out[k] = normalize_json_schema(v)
        elif isinstance(v, list):
            out[k] = [normalize_json_schema(x) for x in v]
        else:
            out[k] = v
    return out


def declarations_to_openai_tools(decls: List[Json]) -> List[Json]:
    tools = []
    for d in decls:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d.get("description", ""),
                    "parameters": normalize_json_schema(
                        d.get("parameters", {"type": "object", "properties": {}})
                    ),
                },
            }
        )
    return tools


def declarations_to_anthropic_tools(decls: List[Json]) -> List[Json]:
    out = []
    for d in decls:
        out.append(
            {
                "name": d["name"],
                "description": d.get("description", ""),
                "input_schema": normalize_json_schema(
                    d.get("parameters", {"type": "object", "properties": {}})
                ),
            }
        )
    return out
