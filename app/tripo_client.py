"""
Tripo3D OpenAPI 同期クライアント（画像→モデルファイル）。
公式 Python SDK と同じエンドポイント: https://api.tripo3d.ai/v2/openapi
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import requests

DEFAULT_BASE_URL = "https://api.tripo3d.ai/v2/openapi"
DEFAULT_MODEL_VERSION = "v2.5-20250123"

_MODEL_EXTS = frozenset({".glb", ".gltf", ".obj", ".fbx", ".stl", ".ply"})


class TripoClientError(Exception):
    pass


def _extension_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    ext = Path(path).suffix.lower()
    if ext in _MODEL_EXTS:
        return ext
    return ".glb"


class TripoClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL):
        self.api_key = api_key or os.environ.get("TRIPO_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError(
                "TRIPO_API_KEY が未設定です。.env または環境変数を設定してください。"
            )
        if not self.api_key.startswith("tsk_"):
            raise ValueError("Tripo API キーは tsk_ で始まる必要があります。")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}"

    def _raise_for_api(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise TripoClientError(f"Invalid JSON ({resp.status_code}): {resp.text[:500]}") from e
        if resp.status_code >= 400:
            msg = data.get("message", data)
            raise TripoClientError(f"HTTP {resp.status_code}: {msg}")
        code = data.get("code")
        if code is not None and code != 0:
            raise TripoClientError(
                f"API code {code}: {data.get('message', data)} "
                f"{data.get('suggestion', '')}"
            )
        return data

    def _ext_to_format(self, path: str) -> str:
        ext = Path(path).suffix.lower().replace(".", "")
        if ext in ("jpg", "jpeg"):
            return "jpeg"
        if ext == "png":
            return "png"
        if ext == "webp":
            return "webp"
        return "jpeg"

    def _build_file_field(self, image_path: str) -> Dict[str, Any]:
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        if str(image_path).startswith(("http://", "https://")):
            return {"type": self._ext_to_format(str(image_path)), "url": str(image_path)}
        token = self._upload_local_file(str(p))
        fmt = self._ext_to_format(str(p))
        return {"type": fmt, "file_token": token}

    def _upload_local_file(self, file_path: str) -> str:
        """POST /upload — multipart、戻り image_token（公式 legacy 実装と同様）。"""
        url = self._url("/upload")
        name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            resp = self.session.post(
                url,
                files={"file": (name, f, "application/octet-stream")},
                timeout=300,
            )
        data = self._raise_for_api(resp)
        inner = data.get("data") or {}
        tok = inner.get("image_token") or inner.get("file_token")
        if not tok:
            raise TripoClientError(f"Upload response missing token: {data}")
        return str(tok)

    def create_image_task(
        self,
        image_path: str,
        *,
        model_version: str = DEFAULT_MODEL_VERSION,
        face_limit: int = 30000,
        texture: bool = True,
        pbr: bool = True,
        texture_quality: str = "detailed",
        geometry_quality: str = "standard",
        texture_alignment: str = "original_image",
        auto_size: bool = False,
        orientation: str = "default",
        quad: bool = False,
    ) -> str:
        """
        image_to_model タスクを投入。task_id を返す。
        quad/auto_size/orientation は公式 SDK 既定に合わせる（quad=True だと OBJ/FBX になりやすい）。
        """
        file_field = self._build_file_field(image_path)
        payload: Dict[str, Any] = {
            "type": "image_to_model",
            "file": file_field,
            "model_version": model_version,
            "face_limit": face_limit,
            "texture": texture,
            "pbr": pbr,
            "texture_quality": texture_quality,
            "geometry_quality": geometry_quality,
            "texture_alignment": texture_alignment,
            "auto_size": auto_size,
            "orientation": orientation,
            "quad": quad,
        }
        url = self._url("/task")
        resp = self.session.post(url, json=payload, timeout=60)
        data = self._raise_for_api(resp)
        inner = data.get("data") or {}
        tid = inner.get("task_id")
        if not tid:
            raise TripoClientError(f"create_task missing task_id: {data}")
        return str(tid)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        url = self._url(f"/task/{task_id}")
        resp = self.session.get(url, timeout=60)
        data = self._raise_for_api(resp)
        return data.get("data") or {}

    def wait_for_task(
        self,
        task_id: str,
        *,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = self.get_task(task_id)
            status = (task.get("status") or "").lower()
            prog = task.get("progress", 0)
            if verbose:
                print(f"[Tripo] {task_id} status={status} progress={prog}")
            if status == "success":
                return task
            if status in ("failed", "cancelled", "banned", "expired"):
                err = task.get("error_msg") or task.get("message") or status
                raise TripoClientError(f"Task {status}: {err}")
            time.sleep(poll_interval)
        raise TripoClientError(f"Timeout waiting for task {task_id}")

    @staticmethod
    def model_url_from_task(task: Dict[str, Any]) -> str:
        out = task.get("output") or {}
        url = out.get("pbr_model") or out.get("model")
        if not url:
            raise TripoClientError(f"No model URL in task output: {out}")
        return str(url)

    @staticmethod
    def _validate_downloaded_file(path: str, ext: str) -> None:
        """保存済みファイルがフォーマットらしいか軽く検査する。"""
        try:
            with open(path, "rb") as f:
                head = f.read(256)
        except OSError as e:
            raise TripoClientError(f"Could not read downloaded file: {e}") from e

        if not head:
            raise TripoClientError("Downloaded file is empty")

        ext = ext.lower()
        if ext == ".glb":
            if head[:4] != b"glTF":
                sneak = head[:200].decode("utf-8", errors="replace")
                raise TripoClientError(
                    f"Expected GLB magic glTF, got {head[:20]!r}. Snippet: {sneak!r}"
                )
        elif ext == ".gltf":
            s = head.lstrip()
            if not s.startswith(b"{"):
                sneak = head[:200].decode("utf-8", errors="replace")
                raise TripoClientError(f"Expected JSON glTF, snippet: {sneak!r}")
        else:
            # HTML / XML エラーページの混入を弾く
            stripped = head.lstrip()
            if stripped.startswith(b"<") or stripped.startswith(b"<!DOCTYPE"):
                sneak = head[:200].decode("utf-8", errors="replace")
                raise TripoClientError(f"Download looks like HTML, not {ext}: {sneak!r}")

    def download_model(self, url: str, save_dir: str, base_name: str) -> str:
        """
        CDN からモデルを取得して save_dir / {base_name}{ext} に保存。
        Authorization ヘッダは付けない（一部 CDN で本文が壊れるのを避ける）。
        URL パスから拡張子を推定、なければ .glb。
        """
        ext = _extension_from_url(url)
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        out_path = os.path.join(save_dir, f"{base_name}{ext}")

        try:
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
        except requests.RequestException as e:
            raise TripoClientError(f"Model download failed: {e}") from e

        self._validate_downloaded_file(out_path, ext)
        return out_path
