"""Tripo3D など長時間処理を `st.status` で段階表示するユーティリティ。

使用例::

    with PipelineStatus("Tripo3D で 3D メッシュを生成中…") as p:
        p.step("画像を Tripo に送信")
        task_id = client.create_image_task(...)
        p.write(f"task_id = {task_id}")
        p.step("Tripo で生成中（推定 60〜120 秒）")
        task = client.wait_for_task(...)
        p.step("GLB をダウンロード")
        client.download_model(...)
        p.done("完了")
"""
from __future__ import annotations

from typing import Optional

import streamlit as st


class PipelineStatus:
    def __init__(self, initial_label: str, expanded: bool = True) -> None:
        self._initial = initial_label
        self._expanded = expanded
        self._status = None  # set in __enter__

    def __enter__(self) -> "PipelineStatus":
        self._status = st.status(self._initial, expanded=self._expanded)
        self._status.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            try:
                self._status.update(label=f"エラー: {exc_val}", state="error")
            except Exception:
                pass
        self._status.__exit__(exc_type, exc_val, exc_tb)

    # ---- API ----

    def step(
        self,
        label: str,
        detail: Optional[str] = None,
        *,
        write: Optional[str] = None,
    ) -> None:
        """ラベルを更新し、ステップ進捗を `running` 状態にする。

        2 つ目の引数は位置引数でもキーワード引数 (`write=...`) でも受け取れる。
        """
        try:
            self._status.update(label=label, state="running")
        except Exception:
            pass
        text = write if write is not None else detail
        if text:
            self.write(text)

    def write(self, text: str) -> None:
        try:
            self._status.write(text)
        except Exception:
            pass

    def done(self, label: str = "完了") -> None:
        try:
            self._status.update(label=label, state="complete", expanded=False)
        except Exception:
            pass

    def error(self, label: str) -> None:
        try:
            self._status.update(label=label, state="error")
        except Exception:
            pass
