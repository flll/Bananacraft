"""Mojang 公式バニラアセット (client jar) の自動取得と PNG 抽出。

Streamlit 非依存の小さなクライアント。`requests` のみ使用 (既存依存)。

公開 API:

- ``fetch_latest_version_info(channel="release") -> dict``
- ``download_client_jar(version_info, cache_root) -> Path``
- ``extract_block_textures(jar_path, dest_dir) -> dict[str, Path]``
- ``ensure_official_assets(cache_root=None, on_progress=None) -> dict | None``

ライセンス注意:

このモジュールは Mojang 公式の version manifest 経由で client.jar を
**ローカルキャッシュにダウンロード**するだけで、Bananacraft の配布物には
jar を同梱しない。ユーザー個人マシンでのテクスチャ抽出は Minecraft EULA
の私的利用範囲に収まる解釈で運用する。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# 定数 / パス
# ---------------------------------------------------------------------

VERSION_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)

DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "bananacraft" / "mc"

# 過度な巨大応答を弾く: client.jar は典型例で ~30MB 程度
MAX_VERSION_JSON_BYTES = 2 * 1024 * 1024
MAX_JAR_BYTES = 80 * 1024 * 1024
MAX_MANIFEST_BYTES = 1 * 1024 * 1024

NETWORK_TIMEOUT = 30  # seconds

# Mojang 側がブロックしないようマナー UA を付与
_USER_AGENT = "Bananacraft/0.1 (jar-fetcher; +https://github.com/local/bananacraft)"


ProgressCallback = Callable[[str, str], None]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _http_get(url: str, *, max_bytes: int) -> bytes:
    """size limit 付きの GET。`requests` 失敗時は例外を上に投げる。"""
    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    with requests.get(
        url, headers=headers, timeout=NETWORK_TIMEOUT, stream=True
    ) as r:
        r.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"response from {url} exceeded {max_bytes} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)


def _sha1_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _emit(progress: Optional[ProgressCallback], stage: str, message: str) -> None:
    if progress is None:
        return
    try:
        progress(stage, message)
    except Exception:  # noqa: BLE001 - 進捗 callback の失敗は本処理を止めない
        logger.debug("on_progress callback failed", exc_info=True)


# ---------------------------------------------------------------------
# Manifest / version JSON
# ---------------------------------------------------------------------


def fetch_latest_version_info(
    *,
    channel: str = "release",
) -> dict:
    """最新の指定チャンネル (release / snapshot) の client jar 情報を返す。

    Returns:
        ``{
            "version": "1.21.1",
            "client_url": "https://piston-data.../client.jar",
            "client_sha1": "...",
            "client_size": 26345678,
        }``

    Raises:
        requests.HTTPError / ValueError / KeyError on network or schema issues.
    """
    if channel not in {"release", "snapshot"}:
        raise ValueError(f"unsupported channel: {channel}")

    raw_manifest = _http_get(VERSION_MANIFEST_URL, max_bytes=MAX_MANIFEST_BYTES)
    import json as _json

    manifest = _json.loads(raw_manifest)
    latest = manifest.get("latest", {})
    target_id = latest.get(channel)
    if not target_id:
        raise KeyError(f"manifest missing latest.{channel}")

    target_url: Optional[str] = None
    for entry in manifest.get("versions", []):
        if entry.get("id") == target_id:
            target_url = entry.get("url")
            break
    if not target_url:
        raise KeyError(f"version {target_id} not found in manifest.versions")

    raw_version = _http_get(target_url, max_bytes=MAX_VERSION_JSON_BYTES)
    version_meta = _json.loads(raw_version)
    client = version_meta.get("downloads", {}).get("client") or {}
    client_url = client.get("url")
    client_sha1 = client.get("sha1")
    client_size = client.get("size")
    if not (client_url and client_sha1):
        raise KeyError(
            f"version {target_id} downloads.client missing url/sha1"
        )

    return {
        "version": str(target_id),
        "client_url": str(client_url),
        "client_sha1": str(client_sha1).lower(),
        "client_size": int(client_size) if client_size is not None else None,
    }


# ---------------------------------------------------------------------
# Jar download
# ---------------------------------------------------------------------


def download_client_jar(
    version_info: dict,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> Path:
    """client.jar を `<cache_root>/<version>/client.jar` に保存。

    既存ファイルの SHA1 が一致すれば再ダウンロードしない (冪等)。

    Returns:
        保存された jar の絶対パス。
    """
    cache_root = Path(cache_root)
    version = version_info["version"]
    expected_sha1 = version_info["client_sha1"].lower()
    url = version_info["client_url"]

    version_dir = cache_root / version
    version_dir.mkdir(parents=True, exist_ok=True)
    jar_path = version_dir / "client.jar"

    if jar_path.exists():
        try:
            existing_sha1 = _sha1_of_file(jar_path)
            if existing_sha1 == expected_sha1:
                _emit(on_progress, "cache", f"jar cached: {jar_path}")
                return jar_path
        except OSError:
            pass

    _emit(on_progress, "download", f"downloading client.jar for {version}")

    headers = {"User-Agent": _USER_AGENT, "Accept": "application/java-archive,*/*"}
    tmp_path = jar_path.with_suffix(".jar.part")
    h = hashlib.sha1()
    total = 0
    try:
        with requests.get(
            url, headers=headers, timeout=NETWORK_TIMEOUT, stream=True
        ) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as out:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_JAR_BYTES:
                        raise ValueError(
                            f"jar exceeded {MAX_JAR_BYTES} bytes (likely wrong URL)"
                        )
                    out.write(chunk)
                    h.update(chunk)
        got_sha1 = h.hexdigest()
        if got_sha1 != expected_sha1:
            raise ValueError(
                f"sha1 mismatch: expected {expected_sha1}, got {got_sha1}"
            )
        os.replace(tmp_path, jar_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    _emit(on_progress, "downloaded", f"client.jar saved ({total} bytes)")
    return jar_path


# ---------------------------------------------------------------------
# PNG extraction
# ---------------------------------------------------------------------


_BLOCK_PNG_RE = re.compile(
    r"^assets/minecraft/textures/block/([a-z0-9_]+)\.png$"
)


def extract_block_textures(
    jar_path: Path | str,
    dest_dir: Path | str,
) -> dict[str, Path]:
    """jar から `assets/minecraft/textures/block/*.png` を抽出。

    Args:
        jar_path: client.jar のパス。
        dest_dir: 抽出先ディレクトリ。存在しなければ作る。

    Returns:
        ``{"minecraft:block/oak_log": <dest>/oak_log.png, ...}`` の辞書。
    """
    jar_path = Path(jar_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Path] = {}
    with zipfile.ZipFile(jar_path, mode="r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            m = _BLOCK_PNG_RE.match(info.filename)
            if not m:
                continue
            stem = m.group(1)
            target = dest_dir / f"{stem}.png"
            # 軽量な冪等性: 既に同サイズで存在すれば書き込み省略
            if target.exists() and target.stat().st_size == info.file_size:
                result[f"minecraft:block/{stem}"] = target
                continue
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            result[f"minecraft:block/{stem}"] = target

    return result


# ---------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------


def ensure_official_assets(
    *,
    cache_root: Path | str | None = None,
    channel: str = "release",
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[dict]:
    """version manifest → jar DL → block PNG 抽出までまとめて実行。

    Returns:
        成功時: ``{"version", "jar_path", "blocks_dir", "textures"}``。
        失敗時 (ネットワーク不通、SHA1 不一致など): ``None``。
        例外はキャッチしてフォールバックを促す。
    """
    root = Path(cache_root) if cache_root is not None else DEFAULT_CACHE_ROOT

    try:
        _emit(on_progress, "manifest", "fetching version manifest")
        version_info = fetch_latest_version_info(channel=channel)
        version = version_info["version"]
        _emit(on_progress, "manifest", f"latest {channel}: {version}")

        jar_path = download_client_jar(
            version_info, cache_root=root, on_progress=on_progress
        )

        blocks_dir = root / version / "blocks"
        _emit(on_progress, "extract", "extracting block textures")
        textures = extract_block_textures(jar_path, blocks_dir)
        _emit(
            on_progress,
            "ready",
            f"extracted {len(textures)} block textures",
        )
    except Exception as exc:  # noqa: BLE001 - フォールバック誘導
        logger.warning("ensure_official_assets failed: %s", exc, exc_info=True)
        _emit(on_progress, "failed", str(exc))
        return None

    return {
        "version": version,
        "jar_path": jar_path,
        "blocks_dir": blocks_dir,
        "textures": textures,
    }


# ---------------------------------------------------------------------
# Cache utilities
# ---------------------------------------------------------------------


def prune_other_versions(
    keep_version: str,
    *,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
) -> int:
    """`keep_version` 以外のサブディレクトリを削除し、削除数を返す。"""
    cache_root = Path(cache_root)
    if not cache_root.is_dir():
        return 0
    removed = 0
    for child in cache_root.iterdir():
        if child.is_dir() and child.name != keep_version:
            try:
                shutil.rmtree(child)
                removed += 1
            except OSError:
                logger.warning("failed to prune %s", child, exc_info=True)
    return removed


__all__ = [
    "VERSION_MANIFEST_URL",
    "DEFAULT_CACHE_ROOT",
    "fetch_latest_version_info",
    "download_client_jar",
    "extract_block_textures",
    "ensure_official_assets",
    "prune_other_versions",
]
