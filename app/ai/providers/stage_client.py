"""工程ごとの LLM 呼び出し（プロバイダ切替）。"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from ..routing import AIStage, Provider, effective_route, resolve_api_key_for_stage, text_model
from .tool_format import declarations_to_anthropic_tools, declarations_to_openai_tools


@dataclass
class ToolCallResult:
    name: str
    arguments: Dict[str, Any]


def _openai_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _anthropic_client(api_key: str):
    from anthropic import Anthropic

    return Anthropic(api_key=api_key)


def complete_text(
    stage: AIStage,
    *,
    system: str,
    user: str,
    temperature: float = 0.4,
    image_bytes: Optional[bytes] = None,
    image_mime: str = "image/jpeg",
) -> str:
    """プレーンテキスト（JSON 強制なし）。"""
    route = effective_route(stage)
    key = resolve_api_key_for_stage(stage)
    model = text_model(stage)

    if route.provider == Provider.GOOGLE:
        client = genai.Client(api_key=key)
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        contents: List[Any] = [user]
        if image_bytes:
            contents.insert(0, types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        return resp.text or ""

    if route.provider == Provider.OPENAI:
        cli = _openai_client(key)
        user_content: Any = user
        if image_bytes:
            b64 = base64.standard_b64encode(image_bytes).decode("ascii")
            user_content = [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{b64}"}},
            ]
        r = cli.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        )
        return r.choices[0].message.content or ""

    if route.provider == Provider.ANTHROPIC:
        cli = _anthropic_client(key)
        blocks: List[Dict[str, Any]] = []
        if image_bytes:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_mime,
                        "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                    },
                }
            )
        blocks.append({"type": "text", "text": user})
        msg = cli.messages.create(
            model=model,
            max_tokens=4096,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": blocks}],
        )
        parts = []
        for b in msg.content:
            if b.type == "text":
                parts.append(b.text)
        return "".join(parts)

    raise RuntimeError(f"Unsupported provider {route.provider}")


def complete_json(
    stage: AIStage,
    *,
    system: str,
    user: str,
    temperature: float = 0.3,
    image_bytes: Optional[bytes] = None,
    image_mime: str = "image/jpeg",
) -> str:
    """JSON またはプレーンテキスト応答を返す（呼び出し側で json.loads）。"""
    route = effective_route(stage)
    key = resolve_api_key_for_stage(stage)
    model = text_model(stage)

    if route.provider == Provider.GOOGLE:
        client = genai.Client(api_key=key)
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
        )
        contents: List[Any] = [user]
        if image_bytes:
            contents.insert(0, types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        return resp.text or ""

    if route.provider == Provider.OPENAI:
        cli = _openai_client(key)
        user_content: Any = user
        if image_bytes:
            b64 = base64.standard_b64encode(image_bytes).decode("ascii")
            user_content = [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{b64}"}},
            ]
        r = cli.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return r.choices[0].message.content or ""

    if route.provider == Provider.ANTHROPIC:
        cli = _anthropic_client(key)
        blocks: List[Dict[str, Any]] = []
        if image_bytes:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_mime,
                        "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                    },
                }
            )
        blocks.append({"type": "text", "text": user})
        msg = cli.messages.create(
            model=model,
            max_tokens=8192,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": blocks}],
        )
        parts = []
        for b in msg.content:
            if b.type == "text":
                parts.append(b.text)
        return "".join(parts)

    raise RuntimeError(f"Unsupported provider {route.provider}")


def complete_with_tools(
    stage: AIStage,
    *,
    system: str,
    user_text: str,
    declarations: List[Dict[str, Any]],
    image_bytes: Optional[bytes] = None,
    image_mime: str = "image/jpeg",
    temperature: float = 0.5,
) -> List[ToolCallResult]:
    route = effective_route(stage)
    key = resolve_api_key_for_stage(stage)
    model = text_model(stage)

    if route.provider == Provider.GOOGLE:
        client = genai.Client(api_key=key)
        oai_tools = declarations_to_openai_tools(declarations)
        tool_config = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t["function"]["name"],
                    description=t["function"].get("description", ""),
                    parameters=t["function"]["parameters"],
                )
                for t in oai_tools
            ]
        )
        contents: List[Any] = [user_text]
        if image_bytes:
            contents.insert(0, types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[tool_config],
                temperature=temperature,
            ),
        )
        return _parse_gemini_tool_response(resp)

    if route.provider == Provider.OPENAI:
        cli = _openai_client(key)
        tools = declarations_to_openai_tools(declarations)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": _openai_user_content(user_text, image_bytes, image_mime),
            },
        ]
        r = cli.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        return _parse_openai_tool_response(r)

    if route.provider == Provider.ANTHROPIC:
        cli = _anthropic_client(key)
        tools = declarations_to_anthropic_tools(declarations)
        content_blocks: List[Dict[str, Any]] = []
        if image_bytes:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_mime,
                        "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                    },
                }
            )
        content_blocks.append({"type": "text", "text": user_text})
        msg = cli.messages.create(
            model=model,
            max_tokens=16384,
            temperature=temperature,
            system=system,
            tools=tools,
            messages=[{"role": "user", "content": content_blocks}],
        )
        return _parse_anthropic_tool_response(msg)

    raise RuntimeError(f"Unsupported provider {route.provider}")


def _openai_user_content(text: str, image_bytes: Optional[bytes], mime: str) -> Any:
    if not image_bytes:
        return text
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]


def _parse_gemini_tool_response(resp) -> List[ToolCallResult]:
    out: List[ToolCallResult] = []
    if not resp.candidates:
        return out
    for c in resp.candidates:
        if not c.content or not c.content.parts:
            continue
        for p in c.content.parts:
            if hasattr(p, "function_call") and p.function_call:
                fc = p.function_call
                args = dict(fc.args) if fc.args else {}
                out.append(ToolCallResult(fc.name, args))
    return out


def _parse_openai_tool_response(resp) -> List[ToolCallResult]:
    out: List[ToolCallResult] = []
    msg = resp.choices[0].message
    if not msg.tool_calls:
        return out
    for tc in msg.tool_calls:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append(ToolCallResult(tc.function.name, args))
    return out


def _parse_anthropic_tool_response(msg) -> List[ToolCallResult]:
    out: List[ToolCallResult] = []
    for b in msg.content:
        if b.type == "tool_use":
            out.append(ToolCallResult(b.name, dict(b.input)))
    return out


def generate_image_bytes(
    *,
    prompt: str,
    reference_image_bytes: Optional[bytes] = None,
    reference_mime: str = "image/jpeg",
) -> Optional[bytes]:
    """画像工程は常に Gemini（参照画像 i2i）。"""
    stage = AIStage.IMAGE_RENDER
    route = effective_route(stage)
    assert route.provider == Provider.GOOGLE
    key = resolve_api_key_for_stage(stage)
    client = genai.Client(api_key=key)
    from ..routing import image_model

    model = image_model(stage)
    contents: List[Any] = [prompt]
    if reference_image_bytes:
        contents.append(types.Part.from_bytes(data=reference_image_bytes, mime_type=reference_mime))
    resp = client.models.generate_content(model=model, contents=contents)
    if resp.candidates and resp.candidates[0].content.parts:
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                return part.inline_data.data
    return None


def anthropic_chat_json_turn(
    *,
    system: str,
    user_message: str,
    history: List[Dict[str, Any]],
    model: str,
    api_key: str,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """1 ターン追加し JSON をパースして返す。history は Claude API 形式の messages。"""
    from anthropic import Anthropic

    cli = Anthropic(api_key=api_key)
    messages = list(history) + [{"role": "user", "content": user_message}]
    msg = cli.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.4,
        system=system,
        messages=messages,
    )
    text = ""
    for b in msg.content:
        if b.type == "text":
            text += b.text
    try:
        cleaned = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
    except Exception:
        parsed = {"reasoning": "parse_error", "image_prompt": user_message}
    new_hist = messages + [{"role": "assistant", "content": text}]
    return parsed, new_hist


def gemini_chat_json_turn(
    *,
    chat_session,
    user_message: str,
) -> Dict[str, Any]:
    """既存 Gemini チャットセッションで 1 ターン。"""
    resp = chat_session.send_message(user_message)
    try:
        if getattr(resp, "parsed", None):
            return resp.parsed
    except Exception:
        pass
    text = resp.text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
