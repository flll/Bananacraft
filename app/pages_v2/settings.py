"""Settings — API キー / World Origin / Terraformer / プロジェクトリセット."""
from __future__ import annotations

import os

import streamlit as st

from ai.browser_keys import clear_persisted_keys, save_persisted_keys
from rcon_client import RconClient
from terraformer import Terraformer
from v2 import mc_assets_prefs as _mc_prefs
from v2 import mc_assets_runtime as _mc_runtime
from v2.tripo_config import (
    MODEL_VERSION_CHOICES,
    QUALITY_CHOICES,
    STYLE_CHOICES,
    TEXTURE_ALIGNMENT_CHOICES,
    TEXTURE_MODEL_VERSION_CHOICES,
    TRIPO_RESET_BUTTON_KEY,
    TripoConfig,
    reset_tripo_config,
    save_tripo_config,
    tripo_reset_confirmed,
)

from ui import state as S
from ui.buttons import danger_button, primary_button, secondary_button
from ui.feature_card import FeatureCard, render_feature_cards


def _section_api_keys() -> None:
    st.subheader("🔑 API キー")
    st.caption(
        "ブラウザの localStorage に保存できます。XSS のあるページではキーが漏洩しうるため、"
        "信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシを推奨します。"
    )
    ctx = st.session_state.api_key_context

    if "sb_gem" not in st.session_state and ctx.get("GEMINI_API_KEY"):
        st.session_state.sb_gem = ctx["GEMINI_API_KEY"]
    if "sb_oai" not in st.session_state and ctx.get("OPENAI_API_KEY"):
        st.session_state.sb_oai = ctx["OPENAI_API_KEY"]
    if "sb_ant" not in st.session_state and ctx.get("ANTHROPIC_API_KEY"):
        st.session_state.sb_ant = ctx["ANTHROPIC_API_KEY"]
    if "sb_tripo" not in st.session_state and ctx.get("TRIPO_API_KEY"):
        st.session_state.sb_tripo = ctx["TRIPO_API_KEY"]

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("GEMINI_API_KEY", type="password", key="sb_gem",
                      help="画像生成・コンセプト・ゾーニング・装飾分析")
        st.text_input("OPENAI_API_KEY", type="password", key="sb_oai",
                      help="フォールバック用 (Architect FC など)")
    with c2:
        st.text_input("ANTHROPIC_API_KEY", type="password", key="sb_ant",
                      help="フォールバック用 (コンセプト対話など)")
        st.text_input("TRIPO_API_KEY", type="password", key="sb_tripo",
                      help="画像から 3D メッシュ生成 (`tsk_` で始まる)")

    for wkey, env in (
        ("sb_gem", "GEMINI_API_KEY"),
        ("sb_oai", "OPENAI_API_KEY"),
        ("sb_ant", "ANTHROPIC_API_KEY"),
        ("sb_tripo", "TRIPO_API_KEY"),
    ):
        v = st.session_state.get(wkey, "")
        if isinstance(v, str) and v.strip():
            ctx[env] = v.strip()
    S.apply_api_keys_to_env()

    c_save, c_clr = st.columns(2)
    with c_save:
        if secondary_button("💾 ブラウザに保存", key="bnn_set_save_keys", use_container_width=True,
                            help="localStorage に書き込み"):
            try:
                save_persisted_keys(ctx)
                st.success("保存しました")
            except Exception as e:
                st.warning(str(e))
    with c_clr:
        if danger_button(
            "🗑️ ブラウザから削除",
            key="bnn_set_clear_keys",
            confirm_title="保存済み API キーを削除しますか？",
            confirm_body="localStorage と現在のセッションから API キーが消えます。次回また入力が必要です。",
            confirm_label="削除する",
            use_container_width=True,
        ):
            clear_persisted_keys()
            for wkey in ("sb_gem", "sb_oai", "sb_ant", "sb_tripo"):
                st.session_state.pop(wkey, None)
            st.session_state.api_key_context = {}
            st.session_state._browser_keys_hydrated = False
            S.apply_api_keys_to_env()
            st.toast("削除しました。", icon="🧹")
            st.rerun()


def _section_world_origin() -> None:
    st.subheader("🌍 Minecraft World Origin")
    st.caption("建設範囲の南西の原点ブロック。建物・インフラ・装飾の絶対座標はここに加算されます。")
    fm = st.session_state.get("file_manager")
    ox, oy, oz = S.project_origin()
    c1, c2, c3 = st.columns(3)
    with c1:
        n_x = st.number_input("Origin X", value=int(ox), key="bnn_set_ox")
    with c2:
        n_y = st.number_input("Origin Y", value=int(oy), key="bnn_set_oy")
    with c3:
        n_z = st.number_input("Origin Z", value=int(oz), key="bnn_set_oz")
    if primary_button("💾 Save Origin", key="bnn_set_save_origin",
                       disabled=fm is None):
        S.save_project_origin(int(n_x), int(n_y), int(n_z))
        st.toast("Saved!", icon="💾")


def _section_tripo() -> None:
    # --- Phase 0: リセット (widget 描画より前) ----------------------------
    if tripo_reset_confirmed(st.session_state):
        defaults = reset_tripo_config()
        st.session_state.tripo_config = defaults
        defaults.apply_widget_state(st.session_state)
        st.toast("Tripo 設定をリセットしました。", icon="🔄")
        st.rerun()

    cfg: TripoConfig = st.session_state.tripo_config

    # --- Phase 1: 欠落 widget key の seed ---------------------------------
    cfg.ensure_widget_keys(st.session_state)

    st.subheader("🧊 Tripo3D 設定")
    st.markdown(
        "**Tripo3D って何？** — Structure 画像（白黒のシルエット）から **3D メッシュ（GLB）** を作る AI サービス。"
        "Bananacraft では、その GLB を**ボクセル化 → Minecraft ブロックに割当**してから RCON で建てます。"
    )
    st.markdown(
        "**建物ごとのサイズは City Plan のゾーン `width × depth` から自動で決まります。**"
        " ここでは Tripo3D のスタイル・テクスチャなどの全体パラメータだけを調整します。"
        " 解像度を細かく上書きしたいときは下の **⚙️ 上級者モード** を開いてください。"
    )
    st.caption(
        "💾 保存先: `~/.config/bananacraft/tripo_config.json`（プロジェクトを跨いで永続化）。"
        "「デフォルトに戻す」で初期値に復帰します。"
    )

    advanced = st.toggle(
        "⚙️ 上級者モード（Tripo の細かい調整）",
        key="bnn_tripo_advanced",
        help=(
            "建物の規模は City Plan のゾーン width × depth から自動で決まります。"
            " ここでチェックすると、voxel 解像度 / stylize block_size / seed などの"
            " 手動上書き UI が表示されます。"
        ),
    )

    if not advanced:
        st.caption(
            "💡 建物ごとの規模はゾーンサイズから自動算出されます。"
            "解像度を細かく調整したいときだけ上級者モードを開いてください。"
        )

    style_widget_val = str(st.session_state.get("bnn_tripo_style", TripoConfig.style_to_widget(cfg.style)))
    style_options = list(STYLE_CHOICES)
    if style_widget_val not in style_options:
        style_options = [style_widget_val] + style_options

    # --- Phase 2: widget 描画 --------------------------------------------
    # --- Model -----------------------------------------------------------
    with st.expander("🧠 Model（モデル）— Tripo3D 本体のバージョンと後処理スタイル", expanded=True):
        st.info(
            "**何のための設定？**\n\n"
            "- どの Tripo3D モデルで 3D 化するか（バージョン）\n"
            "- 出力メッシュに**後段で適用するスタイル**（minecraft / voxel / lego / voronoi）\n\n"
            "**いつ触る？** → 普段は触らなくて OK。"
            "出力がカクカクしすぎ／滑らかすぎでブロック化が破綻するときに `style` を切り替える。\n\n"
            "ℹ️ `style` は image_to_model の後段で **`stylize_model`** という別タスクとして適用されます"
            "（Tripo クレジット追加消費、+60〜120 秒）。",
            icon="🧠",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox(
                "model_version（Tripo3D モデルのバージョン）",
                options=MODEL_VERSION_CHOICES,
                key="bnn_tripo_mv",
                help=(
                    "Tripo3D の **image_to_model**（画像→3D メッシュ）AI モデルのバージョン。\n"
                    "新しいほど精度が高い。互換性問題が出ない限り最新（v2.5）でよい。\n\n"
                    "※ `v3.0-20250812` は **texture_model 専用** のバージョン番号で、\n"
                    "image_to_model には存在しません。下の「🖌️ Texture Model」セクションで選択できます。"
                ),
            )
            st.caption(
                "📦 ここは **形状を作る image_to_model API** のバージョン。"
                "テクスチャ専用の `v3.0-20250812` を使いたい場合は、下の **🖌️ Texture Model** セクションへ。"
            )
        with c2:
            st.selectbox(
                "style（後処理スタイル / stylize_model）",
                options=style_options,
                key="bnn_tripo_style",
                help=(
                    "image_to_model 完了後に **stylize_model タスク** で適用する後処理スタイル。\n\n"
                    "・None: スタイル適用なし。ベースメッシュをそのままボクセル化\n"
                    "・minecraft: Tripo 側で **Minecraft 風ブロックメッシュ**に変換（Bananacraft では最も相性◎）\n"
                    "・voxel: 汎用ボクセル風\n"
                    "・lego: レゴ風\n"
                    "・voronoi: ボロノイ分割風（装飾的）"
                ),
            )
            st.caption(
                "🧱 **`minecraft` 推奨**: Tripo がメッシュを Minecraft ブロックの単位に揃えてから返してくれるので、"
                "そのあとのボクセル化＋色マッチが最も自然に決まります。"
            )

        active_style = TripoConfig.style_from_widget(
            st.session_state.get("bnn_tripo_style")
        )
        if active_style:
            if advanced:
                st.slider(
                    f"style_block_size（{active_style} の粒度）",
                    min_value=20,
                    max_value=160,
                    step=10,
                    key="bnn_tripo_style_bs",
                    help=(
                        "stylize_model に渡す block_size。\n"
                        "小さいほど 1 ブロックが細かく、ブロック数が増える。\n"
                        "大きいほど粗いがシルエットがハッキリする。\n"
                        "通常はゾーンサイズから自動算出されます。"
                        " 手動で固定したいときに上級者モードでここを触ってください。"
                    ),
                )
            else:
                st.caption(
                    f"🤖 `style_block_size` はゾーン最長辺から自動算出されます。"
                    f" 現在の保存値: {int(st.session_state.get('bnn_tripo_style_bs', cfg.style_block_size))}（fallback）"
                )

    # --- Geometry --------------------------------------------------------
    with st.expander("📐 Geometry（ジオメトリ）— メッシュの形状の細かさ", expanded=False):
        st.info(
            "**何のための設定？**\n\n"
            "Tripo3D が出力する 3D メッシュの**ポリゴン数（=形状の細かさ）**を制御します。"
            "細かいほど元画像に忠実だが、Tripo のクレジット消費と生成時間が増えます。\n\n"
            "**いつ触る？**\n"
            "- 建物の細部（柱、窓枠、装飾）が消える → `geometry_quality=detailed` ＋ `face_limit` を増やす\n"
            "- クレジット節約／生成時間短縮したい → `face_limit` を下げる",
            icon="📐",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.selectbox(
                "geometry_quality（形状の精密さ）",
                options=QUALITY_CHOICES,
                key="bnn_tripo_gq",
                help=(
                    "・standard: バランス重視（推奨）\n"
                    "・detailed: 細部が出るが生成時間とクレジット消費が大幅増"
                ),
            )
        with c2:
            st.slider(
                "face_limit（最大ポリゴン数）",
                min_value=1000,
                max_value=100000,
                step=1000,
                key="bnn_tripo_face",
                    help=(
                        "メッシュを構成する三角形の上限。\n"
                        "多いほど細部が出るが、ボクセル化の処理時間も増える。\n"
                        "30000 が建物用途の標準値。"
                ),
            )
        with c3:
            st.checkbox(
                "quad（四角ポリゴン）",
                key="bnn_tripo_quad",
                help=(
                    "出力メッシュを三角形ではなく四角形ベースにする。\n"
                    "ブラウザでの GLB プレビューが綺麗になるが、Minecraft 化には影響しないので **OFF 推奨**。"
                ),
            )
            st.checkbox(
                "auto_size（自動サイズ補正）",
                key="bnn_tripo_autosize",
                help=(
                    "Tripo 側でメッシュの寸法を自動補正する。\n"
                    "Bananacraft 側で footprint をクランプしているので **OFF 推奨**（ONにすると区画サイズとズレる）。"
                ),
            )

    # --- Texture ---------------------------------------------------------
    with st.expander("🎨 Texture（テクスチャ）— メッシュの「色」をどう塗るか", expanded=False):
        st.info(
            "**何のための設定？**\n\n"
            "Tripo3D が生成する**メッシュ表面の色情報**の設定。"
            "Bananacraft はこの色を読んで「最も近い Minecraft ブロック」を選ぶので、"
            "**この設定が最終的なブロック選択（≒見た目の再現度）を左右します**。\n\n"
            "**いつ触る？**\n"
            "- 「原木が茶色羊毛になる」「ハニカムが黄色コンクリになる」等、色が違うブロックに化ける → `texture_alignment=original_image`／`texture_quality=detailed` を維持\n"
            "- 完全に形だけ欲しい（色は気にしない） → `texture` を OFF にして高速化",
            icon="🎨",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.selectbox(
                "texture_quality（テクスチャ精度）",
                options=QUALITY_CHOICES,
                key="bnn_tripo_tq",
                help=(
                    "・standard: 速いが色がぼやけがち\n"
                    "・detailed: 元画像の色を細かく再現 → Minecraft ブロック選択の精度が上がる（推奨）"
                ),
            )
        with c2:
            st.selectbox(
                "texture_alignment（色の貼り方）",
                options=TEXTURE_ALIGNMENT_CHOICES,
                key="bnn_tripo_ta",
                help=(
                    "テクスチャをメッシュに貼る基準。\n\n"
                    "・original_image: 元の concept art の色を優先（推奨：色の再現度が高い）\n"
                    "・geometry: メッシュ形状に最適化（色がズレることがある）"
                ),
            )
        with c3:
            st.checkbox(
                "texture（テクスチャを生成）",
                key="bnn_tripo_tex",
                help=(
                    "OFFにすると Tripo は色情報のないグレーメッシュを返す。\n"
                    "色ではなく形だけ欲しい用途（テスト用）以外は **ON 推奨**。"
                ),
            )
            st.checkbox(
                "pbr（物理ベース）",
                key="bnn_tripo_pbr",
                help=(
                    "金属感／粗さなどの PBR マテリアルを出力。\n"
                    "Minecraft はベース色しか使わないので結果には**ほぼ影響しない**が、GLB プレビューで質感が見えるので ON 推奨。"
                ),
            )

    # --- Texture Model (post-process) -----------------------------------
    with st.expander(
        "🖌️ Texture Model（後段テクスチャ精製）— 色再現を本気で詰めたい時用",
        expanded=False,
    ):
        st.info(
            "**何のための設定？**\n\n"
            "image_to_model で出力した 3D メッシュに対して、**テクスチャだけをもう一度高品質に焼き直す** "
            "後段 API ([`texture_model`](https://docs.tripo3d.ai/texture/texture-model-v3-0-20250812.html))。"
            "ベースメッシュの形はそのままに、表面の色解像度・忠実度だけを底上げします。\n\n"
            "**いつ触る？**\n"
            "- 🎯 「コンセプトアートの細かな色合いまで再現したい」 → ON\n"
            "- 💸 Tripo クレジットの追加消費 (`detailed` なら +10 cr) を惜しまない時\n"
            "- 🪙 普段は OFF で OK（1 段階で十分な品質が出る）\n\n"
            "**フロー**: 画像 → `image_to_model` → ベース GLB → `texture_model` → 高品質 GLB → ボクセル化\n\n"
            "ℹ️ ここの `texture_model_version`（`v3.0-20250812` など）は、上の **🧠 Model** セクションの "
            "`model_version` とは**別の API のバージョン体系**です。混同しないように。",
            icon="🖌️",
        )

        st.checkbox(
            "Texture Model を使う（後段でテクスチャを再生成）",
            key="bnn_tripo_use_tex_model",
            help=(
                "ONにすると image_to_model 完了後に texture_model タスクを追加で実行。\n"
                "クレジット消費と生成時間が増えるが、色の再現度が上がる。"
            ),
        )

        if st.session_state.get("bnn_tripo_use_tex_model"):
            c1, c2 = st.columns(2)
            with c1:
                tex_mv_options = list(TEXTURE_MODEL_VERSION_CHOICES)
                tmv_val = str(st.session_state.get("bnn_tripo_tex_mv", cfg.texture_model_version))
                if tmv_val not in tex_mv_options:
                    tex_mv_options = [tmv_val] + tex_mv_options
                st.selectbox(
                    "texture_model_version",
                    options=tex_mv_options,
                    key="bnn_tripo_tex_mv",
                    help=(
                        "・v3.0-20250812: 最新・最高品質（推奨）\n"
                        "・v2.5-20250123: 旧版。互換性確認用"
                    ),
                )
                st.caption("📚 [API ドキュメント](https://docs.tripo3d.ai/texture/texture-model-v3-0-20250812.html)")
            with c2:
                st.checkbox(
                    "bake（テクスチャ焼き付け）",
                    key="bnn_tripo_tex_bake",
                    help=(
                        "ONで PBR マテリアル効果をベーステクスチャに焼き込む。\n"
                        "GLB として持ち運びしやすくなる。基本 ON 推奨。"
                    ),
                )
            st.caption(
                "💡 `texture_quality` / `texture_alignment` / `texture_seed` / `pbr` の値は "
                "上の **🎨 Texture** と **🎲 Seed** セクションの設定が使われます。"
            )
        else:
            st.caption("チェックすると詳細設定が表示されます。")

    # --- Voxel resolution (advanced only) -------------------------------
    if advanced:
      with st.expander("🧱 Voxel 解像度（手動上書き）", expanded=False):
        st.info(
            "**何のための設定？**\n\n"
            "Tripo3D が出した滑らかなメッシュを**何ブロック四方の解像度でボクセル化するか**を決めます。"
            "**1 voxel = 1 Minecraft ブロック** なので、これが直接「建物のブロック数」になります。\n\n"
            "通常はゾーン `max(width, depth)` から自動算出されます（下のチェックボックスで OFF にできます）。"
            "**ここで触った値は、自動上書きを OFF にした場合の fallback** になります。\n\n"
            "計算式: `target_voxel = max(lower, min(upper, max(width, depth)))`\n"
            "（建物の縦／横の長い方を、lower〜upper の範囲にクランプ）\n\n"
            "**目安（表面ブロック数 ≒ 6 × target_voxel²）**:\n"
            "- ⬛ `lo=1, hi=1` → **~6 blocks**（極小・シルエットのみ。細部はほぼ消える）\n"
            "- 🟦 `lo=4, hi=5` → **~150 blocks**（**Pixel Art**: 1 マス = 1 ブロック、推奨）\n"
            "- 🟢 `lo=6, hi=12` → **~600 blocks**（小屋スケール）\n"
            "- 🟡 `lo=12, hi=24` → **~3000 blocks**（中スケール、立体感あり）\n"
            "- 🔴 `lo=24, hi=48` → **~14000 blocks**（大型・高精細）",
            icon="🧱",
        )

        st.checkbox(
            "ゾーン最長辺から自動上書きする（推奨）",
            key="bnn_tripo_auto_size_from_zone",
            help=(
                "ON のとき、Building Blueprint 作成時に zone の "
                "`max(width, depth)` をそのまま target_blocks として "
                "voxel_lower=voxel_upper, style_block_size を上書きします。\n\n"
                "OFF にすると、ここで設定した lo/hi/block_size がそのまま使われます（旧挙動）。"
            ),
        )

        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "voxel_lower_bound（最小解像度）",
                min_value=1,
                max_value=32,
                key="bnn_tripo_vlo",
                help=(
                    "区画が小さくても保証されるボクセル数の下限（1〜32）。\n"
                    "小さくするほど concept art の 1 ブロックが Minecraft の 1 ブロックに近づく。\n\n"
                    "目安:\n"
                    "・1-2: 極小シルエット (~6-24 blocks、細部ほぼなし)\n"
                    "・4-6: ドット絵スケール (~100-200 blocks)\n"
                    "・8-12: 中スケール (~400-800 blocks)\n"
                    "推奨: 6（Pixel Art なら lo=4）"
                ),
            )
            st.caption("⬇ ブロック数が多すぎ／本家っぽくないなら下げる")
        with c2:
            st.slider(
                "voxel_upper_bound（最大解像度）",
                min_value=1,
                max_value=128,
                key="bnn_tripo_vhi",
                help=(
                    "大規模区画でもブロック数が無限大にならないよう抑える上限（1〜128）。\n"
                    "高くするほど大型建築のディテールが残る。\n\n"
                    "**Pixel Art**: lo=4, hi=5。**極小**: lo=1, hi=1〜2。\n"
                    "推奨: 48 (通常) / 5 (Pixel Art)"
                ),
            )
            st.caption("⬆ 大型建築の細部が欲しいなら上げる ⬇ Pixel Art なら 5 程度")
        vlo = int(st.session_state.get("bnn_tripo_vlo", cfg.voxel_lower_bound))
        vhi = int(st.session_state.get("bnn_tripo_vhi", cfg.voxel_upper_bound))
        if vlo > vhi:
            st.warning(
                "voxel_lower_bound > voxel_upper_bound です。クランプ時に上限が優先されます。",
                icon="⚠️",
            )

        # 簡易プレビュー: 現在の設定での予測ブロック数
        sample_footprints = [
            (1, "1×1 極小"),
            (5, "5×5 小屋"),
            (10, "10×10 区画"),
            (20, "20×20 大型"),
        ]
        preview_lines: list[str] = []
        for fp, label in sample_footprints:
            est = max(vlo, min(vhi, fp))
            est_blocks = int(6 * est * est)
            preview_lines.append(f"- {label}: target_voxel={est} → ~{est_blocks} blocks")
        st.caption(
            "現在の設定での予測ブロック数（表面のみの概算）:\n\n"
            + "\n".join(preview_lines)
        )

    # --- Seed (advanced only) -------------------------------------------
    if advanced:
      with st.expander("🎲 Seed と補助（再現性・前処理）— 同じ結果を再現したい時用", expanded=False):
        st.info(
            "**何のための設定？**\n\n"
            "Tripo3D は同じ画像でも実行のたびに微妙に違う 3D を返します。"
            "**シードを固定すると、同じ画像 → 完全に同じ 3D** が得られます。\n\n"
            "**いつ触る？**\n"
            "- 🔁 「前回の出来高が気に入ったので再現したい」 → シードを記録して同じ値を入れる\n"
            "- 🆕 「もう一回ガチャを引きたい」 → シードを変更（42 → 43 など）\n"
            "- 🧪 入力画像がノイジー／背景が複雑 → `enable_image_autofix` を ON",
            icon="🎲",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.number_input(
                "model_seed（形状の乱数）",
                step=1,
                key="bnn_tripo_mseed",
                    help=(
                        "メッシュ形状の生成シード。\n"
                        "同じ値 → 同じ形が再現される。値を変えると別パターンの 3D を引き直せる。"
                ),
            )
        with c2:
            st.number_input(
                "texture_seed（テクスチャの乱数）",
                step=1,
                key="bnn_tripo_tseed",
                    help=(
                        "テクスチャ生成側のシード。\n"
                        "形状はそのままに、色の塗り直しだけしたい時に変える。"
                ),
            )
        with c3:
            st.checkbox(
                "enable_image_autofix（画像の自動補正）",
                key="bnn_tripo_autofix",
                help=(
                    "Tripo 側で入力画像を自動補正（背景除去、明るさ調整など）してから 3D 化する。\n"
                    "入力が Structure 画像（既にクリーンな白黒）なら不要。\n"
                    "コンセプトアートなど複雑な画像でうまく行かない時に ON にする実験用。"
                ),
            )

    # --- Phase 3: widget → tripo_config 同期 --------------------------------
    cfg = TripoConfig.from_widget_state(st.session_state)
    st.session_state.tripo_config = cfg

    c_save, c_reset = st.columns(2)
    with c_save:
        if primary_button(
            "💾 Tripo 設定を保存",
            key="bnn_tripo_save",
            use_container_width=True,
            help="~/.config/bananacraft/tripo_config.json に書き込み",
        ):
            try:
                save_tripo_config(cfg)
                st.toast("Tripo 設定を保存しました。", icon="💾")
            except OSError as e:
                st.error(f"保存に失敗: {e}")
    with c_reset:
        danger_button(
            "🔄 デフォルトに戻す",
            key=TRIPO_RESET_BUTTON_KEY,
            confirm_title="Tripo 設定をデフォルトに戻しますか？",
            confirm_body=(
                "保存済みの `tripo_config.json` を削除し、初期値"
                "（style=minecraft, auto_size_from_zone=ON など）"
                "にリセットします。"
            ),
            confirm_label="リセットする",
            use_container_width=True,
        )


def _section_minecraft_assets() -> None:
    st.subheader("🧱 Minecraft アセット (公式テクスチャ)")
    st.caption(
        "初回起動時に Mojang 公式 version manifest から最新 release の "
        "`client.jar` を**自動ダウンロード**し、`assets/minecraft/textures/block/` "
        "の PNG を 320×320 のアトラスに焼き直して GLB プレビューに貼り付けます。"
    )

    state = _mc_runtime.get_state()
    stage = state.get("stage", "pending")
    message = state.get("message", "")
    version = state.get("version")
    tex_count = int(state.get("texture_count") or 0)
    jar_path = state.get("jar_path")

    stage_label = {
        "pending": ("⏳ 起動待ち", "info"),
        "manifest": ("🌐 manifest 取得中", "info"),
        "download": ("⬇️ client.jar をダウンロード中", "info"),
        "downloaded": ("📦 jar 検証完了", "info"),
        "extract": ("🗂️ PNG 抽出中", "info"),
        "ready": ("✅ 準備完了", "success"),
        "failed": ("⚠️ 取得失敗 (手作りアトラスで継続)", "warning"),
        "disabled": ("⏸️ 手作りアトラス固定", "info"),
    }.get(stage, (f"ℹ️ {stage}", "info"))

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("ステータス", stage_label[0])
    with col_b:
        st.metric("Minecraft version", version or "—")
    with col_c:
        st.metric("抽出済みテクスチャ", f"{tex_count}" if tex_count else "—")

    if message:
        getattr(st, stage_label[1])(message)

    if jar_path:
        try:
            from pathlib import Path as _P
            size_mb = _P(jar_path).stat().st_size / (1024 * 1024)
            st.caption(f"📦 `{jar_path}` — {size_mb:.1f} MB")
        except OSError:
            st.caption(f"📦 `{jar_path}`")

    prefs = _mc_prefs.load()

    new_force = st.toggle(
        "手作りアトラスを強制使用 (公式 jar を無視)",
        value=bool(prefs.force_procedural),
        key="bnn_mc_force_procedural",
        help=(
            "デバッグやライセンス回避の用途で公式アセットを使わないモード。"
            "ON のまま保存すると次回起動以降も jar の取得をスキップします。"
        ),
    )
    if new_force != prefs.force_procedural:
        prefs.force_procedural = new_force
        _mc_prefs.save(prefs)
        _mc_runtime.set_force_procedural(new_force)
        if new_force:
            st.toast("手作りアトラス固定モードに切り替えました。", icon="✏️")
        else:
            _mc_runtime.restart()
            st.toast("公式アセットの再取得を開始します。", icon="🌐")
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if secondary_button(
            "🔄 アセットを再ダウンロード",
            key="bnn_mc_restart",
        ):
            _mc_runtime.restart()
            st.toast("再ダウンロードを開始しました。", icon="🌐")
            st.rerun()
    with col2:
        if danger_button(
            "🧹 jar キャッシュを削除",
            key="bnn_mc_clear",
            confirm_title="`~/.cache/bananacraft/mc/` を削除しますか?",
            confirm_body=(
                "ダウンロード済みの client.jar と抽出した PNG が全部消えます。"
                "次回プレビュー時に自動で再取得されます。"
            ),
            confirm_label="削除する",
        ):
            removed = _mc_runtime.clear_jar_cache()
            _mc_runtime.restart()
            st.toast(f"{removed} エントリ削除しました。", icon="🧹")
            st.rerun()

    st.caption(
        "ℹ️ ライセンス: Minecraft EULA に従い**個人利用範囲のみ**。"
        "Bananacraft の配布物に jar は同梱されません。"
        "キャッシュ場所: `~/.cache/bananacraft/mc/`"
    )


def _section_terraformer() -> None:
    st.subheader("🚜 Terraformer (Clear 200×200)")
    ox, oy, oz = S.project_origin()
    st.caption(f"Area: ({ox}, {oz}) to ({ox + 200}, {oz + 200}) at Y = {oy}")
    if danger_button(
        "🚜 Terraformer を実行",
        key="bnn_set_run_terra",
        confirm_title="200×200 エリアをクリアしますか？",
        confirm_body=(
            "サーバー上の指定エリアを `fill air` で平らにします。"
            "周囲の地形には影響しませんが、対象エリアの既存ブロックは消えます。"
        ),
        confirm_label="実行する",
    ):
        try:
            with st.spinner("Clearing area & Fixing chunks..."):
                rcon = RconClient()
                terra = Terraformer(rcon)
                logs = terra.terraform((int(ox), int(oy), int(oz)), width=200, depth=200, base_y=int(oy))
                st.success("Terraforming Complete!")
                with st.expander("Logs"):
                    st.write(logs)
        except Exception as e:
            st.error(f"Terraforming Failed: {e}")


def _section_project_management() -> None:
    if not S.has_project():
        return
    st.subheader("📁 プロジェクト")
    st.markdown(f"現在のプロジェクト: `{st.session_state.project_name}`")
    cc1, cc2 = st.columns(2)
    with cc1:
        if secondary_button("⬅️ プロジェクトを閉じる", key="bnn_set_close_proj"):
            S.reset_project()
            st.switch_page("pages_v2/setup.py")
    with cc2:
        if danger_button(
            "🗑️ Restart Project（全消去）",
            key="bnn_set_reset_proj",
            confirm_title="プロジェクトをリセットしますか？",
            confirm_body=(
                "セッション内の全ての状態（コンセプト・ゾーニング・選択中の建物など）が消えます。"
                "保存済みファイル（`projects/<name>/`）は残るので、再度開けば復元できます。"
            ),
            confirm_label="リセットする",
        ):
            S.reset_project()
            st.switch_page("pages_v2/setup.py")


def render() -> None:
    S.ensure_session_defaults()
    st.title("⚙️ Settings")
    st.caption("API キー・原点座標・サーバー操作などの裏方設定。")

    render_feature_cards(
        [
            FeatureCard("🔑", "API キーをまとめて管理",
                        "4 つのプロバイダー（Gemini / OpenAI / Anthropic / Tripo3D）"
                        "を一括設定。ブラウザ保存で次回も即使えます。"),
            FeatureCard("🧊", "Tripo3D をチューニング",
                        "建物ごとの解像度はゾーンサイズから自動算出。"
                        "ここではスタイル・テクスチャなど全体パラメータと、"
                        "上級者モードでの手動上書きが行えます。",
                        meta="`~/.config/bananacraft/tripo_config.json` に永続化"),
            FeatureCard("🌍", "建設地点を指定",
                        "Minecraft サーバー上のどこに建てるかを X/Y/Z で指定。"
                        "建物・インフラは全部この原点を基準に配置されます。"),
            FeatureCard("🚜", "地ならし",
                        "Terraformer で 200×200 のエリアを `fill air` クリアします。"
                        "ワールドの安全な位置で実行してください。"),
        ]
    )
    st.divider()
    _section_api_keys()
    st.divider()
    _section_world_origin()
    st.divider()
    _section_tripo()
    st.divider()
    _section_minecraft_assets()
    st.divider()
    _section_terraformer()
    st.divider()
    _section_project_management()


render()
