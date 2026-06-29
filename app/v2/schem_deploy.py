"""Tripo `.schem` を WorldEdit + RCON でサーバーに配置するヘルパー。

責務:
1. ローカル ``.schem`` を Minecraft サーバーが読める schematics ディレクトリへコピー
2. ``RconClient`` 経由で WorldEdit コマンド列を送信して ``//paste``

設計メモは :doc:`docs/REPOSITORY_DESIGN.md` の §13 を参照。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from rcon_client import RconClient
except ImportError:  # pragma: no cover
    from app.rcon_client import RconClient


class SchemDeployError(Exception):
    """`.schem` のコピー・配置で起きるエラー。"""


def _repo_root() -> Path:
    """Bananacraft リポジトリのルートを返す（``app/v2/`` から 2 階層上）。"""
    return Path(__file__).resolve().parents[2]


def default_schematics_dir() -> Path:
    """サーバーが読む schematics ディレクトリの既定パス。

    優先順位:
        1. 環境変数 ``WORLDEDIT_SCHEM_DIR``
        2. ``<repo>/minecraft-data/plugins/WorldEdit/schematics``
           （[docker-compose.yml](docker-compose.yml) の itzg/minecraft-server
           が ``./minecraft-data:/data`` をマウントしている前提）
    """
    env = os.environ.get("WORLDEDIT_SCHEM_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return _repo_root() / "minecraft-data" / "plugins" / "WorldEdit" / "schematics"


def deploy_schem(
    local_path: str,
    schematic_name: str,
    *,
    schematics_dir: Optional[Path] = None,
) -> Path:
    """ローカル ``.schem`` を schematics ディレクトリへコピーする。

    Args:
        local_path: ``projects/<name>/building_<id>.schem`` 等のパス。
        schematic_name: ``//schem load <name>.schem`` で参照する名前
            （拡張子なしで渡し、ディスク上は ``<name>.schem`` として保存される）。
        schematics_dir: 上書きしたい場合に指定。既定は :func:`default_schematics_dir`。

    Returns:
        コピー先の絶対パス。

    Raises:
        SchemDeployError: ローカル ``.schem`` が存在しない、または schematics
            ディレクトリが存在しない / 書き込めないとき。
    """
    src = Path(local_path)
    if not src.is_file():
        raise SchemDeployError(f"ローカル .schem が見つかりません: {src}")

    target_dir = (schematics_dir or default_schematics_dir()).expanduser()
    if not target_dir.exists():
        raise SchemDeployError(
            f"schematics ディレクトリが存在しません: {target_dir}\n"
            "WorldEdit 入りの Minecraft サーバーが少なくとも 1 度起動している必要があります。"
            " `make mc-up` でサーバーを立ち上げてから再試行してください。"
            " カスタムパスを使う場合は環境変数 WORLDEDIT_SCHEM_DIR を設定します。"
        )
    if not os.access(target_dir, os.W_OK):
        raise SchemDeployError(
            f"schematics ディレクトリに書き込めません: {target_dir}\n"
            "Docker 経由でサーバーを動かしている場合、ホスト側ユーザーに書き込み権限が必要です。"
        )

    safe_name = schematic_name.strip()
    if not safe_name or "/" in safe_name or "\\" in safe_name:
        raise SchemDeployError(f"無効な schematic 名: {schematic_name!r}")

    dst = target_dir / f"{safe_name}.schem"
    shutil.copyfile(src, dst)
    return dst


DEFAULT_WORLD_NAME = "world"


def _resolve_world_name(world_name: Optional[str]) -> str:
    """paste 先のワールド名を解決する。

    優先順位:
        1. 引数で渡された ``world_name``
        2. 環境変数 ``BANANACRAFT_MC_WORLD``
        3. ``"world"`` (itzg/minecraft-server の既定 LEVEL_NAME)
    """
    if world_name:
        return world_name
    env = os.environ.get("BANANACRAFT_MC_WORLD", "").strip()
    if env:
        return env
    return DEFAULT_WORLD_NAME


def build_paste_commands(
    schematic_name: str,
    origin: Tuple[int, int, int],
    *,
    world_name: Optional[str] = None,
) -> List[str]:
    """WorldEdit に schem を ``//paste`` させる RCON コマンド列を組み立てる。

    Server コンソール (RCON) は WorldEdit セッションを持たないため、
    各コマンドの前に **``//world <name>``** で対象ワールドを設定する必要がある。
    ``//pos1`` で paste 基準点を明示し、``//paste -a`` で air をスキップして
    地形を残したまま建物だけ配置する。

    Args:
        schematic_name: ``//schem load <name>.schem`` で読む名前 (拡張子なしで渡し、
            コマンド組み立て時に ``.schem`` を付与する)。
        origin: paste 基準点 (x, y, z)。``building.py`` の ``_build_origin_for``
            と同じ座標系。
        world_name: paste 先のワールド名。未指定なら ``BANANACRAFT_MC_WORLD``
            → ``"world"`` の順に解決する。

    Returns:
        RCON に投げるコマンド文字列のリスト。

    Notes:
        Purpur RCON では ``gamerule sendCommandFeedback`` の前後挟みが
        ``Incorrect argument`` で弾かれることがあるため意図的に省いている。
        サーバーコンソールはログが多めに出るが副作用はない。
    """
    ox, oy, oz = origin
    safe_name = schematic_name.strip()
    if safe_name.lower().endswith(".schem"):
        schem_arg = safe_name
    else:
        schem_arg = f"{safe_name}.schem"
    world = _resolve_world_name(world_name)
    return [
        f"//world {world}",
        f"//pos1 {ox},{oy},{oz}",
        f"//schem load {schem_arg}",
        "//paste -a",
        f"say Bananacraft: pasted {schem_arg} at {ox},{oy},{oz} (world={world})",
    ]


def paste_via_rcon(
    schematic_name: str,
    origin: Tuple[int, int, int],
    *,
    world_name: Optional[str] = None,
    rcon: Optional[RconClient] = None,
) -> List[str]:
    """WorldEdit を RCON 越しに駆動して schem を配置する。

    Args:
        schematic_name: ``//schem load <name>.schem`` で読む名前（拡張子なしで渡す）。
        origin: paste 基準点 (x, y, z)。
        world_name: 任意。複数ワールドがある場合に明示する。
        rcon: テスト時に差し替え可能な :class:`RconClient`。

    Returns:
        サーバーからのレスポンスログ（``RconClient.connect_and_send`` と同じ形）。
    """
    client = rcon or RconClient()
    cmds = build_paste_commands(schematic_name, origin, world_name=world_name)
    return client.connect_and_send(cmds)
