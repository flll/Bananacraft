"""Settings — API キー / World Origin / Terraformer / プロジェクトリセット."""
from __future__ import annotations

import os

import streamlit as st

from ai.browser_keys import clear_persisted_keys, save_persisted_keys
from rcon_client import RconClient
from terraformer import Terraformer
from v2.tripo_config import (
    MODEL_VERSION_CHOICES,
    QUALITY_CHOICES,
    STYLE_CHOICES,
    TEXTURE_ALIGNMENT_CHOICES,
    TEXTURE_MODEL_VERSION_CHOICES,
    TripoConfig,
    reset_tripo_config,
    save_tripo_config,
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
    cfg: TripoConfig = st.session_state.tripo_config

    st.subheader("🧊 Tripo3D 設定")
    st.markdown(
        "**Tripo3D って何？** — Structure 画像（白黒のシルエット）から **3D メッシュ（GLB）** を作る AI サービス。"
        "Bananacraft では、その GLB を**ボクセル化 → Minecraft ブロックに割当**してから RCON で建てます。"
    )
    st.markdown(
        "**ここで触る項目はこの流れ全体（Tripo の生成パラメータ＋内部のボクセル化の細かさ）を制御します。**"
        " 大抵はデフォルトのままで OK。出来高が「思ったより細い／太い」「色が違う」「形が崩れる」ときに該当セクションだけ触ります。"
    )
    st.caption(
        "💾 保存先: `~/.config/bananacraft/tripo_config.json`（プロジェクトを跨いで永続化）。"
        "「デフォルトに戻す」で推奨値（style=voxel / voxel_lower_bound=12）に即復帰できます。"
    )

    style_default = cfg.style if cfg.style is not None else "None"
    if style_default not in STYLE_CHOICES:
        STYLE_CHOICES.insert(0, style_default)

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
            mv_idx = (
                MODEL_VERSION_CHOICES.index(cfg.model_version)
                if cfg.model_version in MODEL_VERSION_CHOICES
                else 0
            )
            cfg.model_version = st.selectbox(
                "model_version（Tripo3D モデルのバージョン）",
                options=MODEL_VERSION_CHOICES,
                index=mv_idx,
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
            st_idx = STYLE_CHOICES.index(style_default)
            chosen_style = st.selectbox(
                "style（後処理スタイル / stylize_model）",
                options=STYLE_CHOICES,
                index=st_idx,
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
            cfg.style = None if chosen_style == "None" else chosen_style
            st.caption(
                "🧱 **`minecraft` 推奨**: Tripo がメッシュを Minecraft ブロックの単位に揃えてから返してくれるので、"
                "そのあとのボクセル化＋色マッチが最も自然に決まります。"
            )

        if cfg.style:
            cfg.style_block_size = int(
                st.slider(
                    f"style_block_size（{cfg.style} の粒度）",
                    min_value=20,
                    max_value=160,
                    value=int(cfg.style_block_size),
                    step=10,
                    key="bnn_tripo_style_bs",
                    help=(
                        "stylize_model に渡す block_size。\n"
                        "小さいほど 1 ブロックが細かく、ブロック数が増える。\n"
                        "大きいほど粗いがシルエットがハッキリする。\n"
                        "デフォルト 80。Minecraft スケールで 1:1 を狙うなら 40〜60 がおすすめ。"
                    ),
                )
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
            gq_idx = (
                QUALITY_CHOICES.index(cfg.geometry_quality)
                if cfg.geometry_quality in QUALITY_CHOICES
                else 0
            )
            cfg.geometry_quality = st.selectbox(
                "geometry_quality（形状の精密さ）",
                options=QUALITY_CHOICES,
                index=gq_idx,
                key="bnn_tripo_gq",
                help=(
                    "・standard: バランス重視（推奨）\n"
                    "・detailed: 細部が出るが生成時間とクレジット消費が大幅増"
                ),
            )
        with c2:
            cfg.face_limit = int(
                st.slider(
                    "face_limit（最大ポリゴン数）",
                    min_value=1000,
                    max_value=100000,
                    value=int(cfg.face_limit),
                    step=1000,
                    key="bnn_tripo_face",
                    help=(
                        "メッシュを構成する三角形の上限。\n"
                        "多いほど細部が出るが、ボクセル化の処理時間も増える。\n"
                        "30000 が建物用途の標準値。"
                    ),
                )
            )
        with c3:
            cfg.quad = st.checkbox(
                "quad（四角ポリゴン）",
                value=bool(cfg.quad),
                key="bnn_tripo_quad",
                help=(
                    "出力メッシュを三角形ではなく四角形ベースにする。\n"
                    "ブラウザでの GLB プレビューが綺麗になるが、Minecraft 化には影響しないので **OFF 推奨**。"
                ),
            )
            cfg.auto_size = st.checkbox(
                "auto_size（自動サイズ補正）",
                value=bool(cfg.auto_size),
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
            tq_idx = (
                QUALITY_CHOICES.index(cfg.texture_quality)
                if cfg.texture_quality in QUALITY_CHOICES
                else 1
            )
            cfg.texture_quality = st.selectbox(
                "texture_quality（テクスチャ精度）",
                options=QUALITY_CHOICES,
                index=tq_idx,
                key="bnn_tripo_tq",
                help=(
                    "・standard: 速いが色がぼやけがち\n"
                    "・detailed: 元画像の色を細かく再現 → Minecraft ブロック選択の精度が上がる（推奨）"
                ),
            )
        with c2:
            ta_idx = (
                TEXTURE_ALIGNMENT_CHOICES.index(cfg.texture_alignment)
                if cfg.texture_alignment in TEXTURE_ALIGNMENT_CHOICES
                else 0
            )
            cfg.texture_alignment = st.selectbox(
                "texture_alignment（色の貼り方）",
                options=TEXTURE_ALIGNMENT_CHOICES,
                index=ta_idx,
                key="bnn_tripo_ta",
                help=(
                    "テクスチャをメッシュに貼る基準。\n\n"
                    "・original_image: 元の concept art の色を優先（推奨：色の再現度が高い）\n"
                    "・geometry: メッシュ形状に最適化（色がズレることがある）"
                ),
            )
        with c3:
            cfg.texture = st.checkbox(
                "texture（テクスチャを生成）",
                value=bool(cfg.texture),
                key="bnn_tripo_tex",
                help=(
                    "OFFにすると Tripo は色情報のないグレーメッシュを返す。\n"
                    "色ではなく形だけ欲しい用途（テスト用）以外は **ON 推奨**。"
                ),
            )
            cfg.pbr = st.checkbox(
                "pbr（物理ベース）",
                value=bool(cfg.pbr),
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

        cfg.use_texture_model = st.checkbox(
            "Texture Model を使う（後段でテクスチャを再生成）",
            value=bool(cfg.use_texture_model),
            key="bnn_tripo_use_tex_model",
            help=(
                "ONにすると image_to_model 完了後に texture_model タスクを追加で実行。\n"
                "クレジット消費と生成時間が増えるが、色の再現度が上がる。"
            ),
        )

        if cfg.use_texture_model:
            c1, c2 = st.columns(2)
            with c1:
                tmv_default = (
                    cfg.texture_model_version
                    if cfg.texture_model_version in TEXTURE_MODEL_VERSION_CHOICES
                    else TEXTURE_MODEL_VERSION_CHOICES[0]
                )
                cfg.texture_model_version = st.selectbox(
                    "texture_model_version",
                    options=TEXTURE_MODEL_VERSION_CHOICES,
                    index=TEXTURE_MODEL_VERSION_CHOICES.index(tmv_default),
                    key="bnn_tripo_tex_mv",
                    help=(
                        "・v3.0-20250812: 最新・最高品質（推奨）\n"
                        "・v2.5-20250123: 旧版。互換性確認用"
                    ),
                )
                st.caption("📚 [API ドキュメント](https://docs.tripo3d.ai/texture/texture-model-v3-0-20250812.html)")
            with c2:
                cfg.texture_bake = st.checkbox(
                    "bake（テクスチャ焼き付け）",
                    value=bool(cfg.texture_bake),
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

    # --- Voxel resolution -----------------------------------------------
    with st.expander("🧱 Voxel 解像度（ブロック化の細かさ）— 一番重要！", expanded=True):
        st.info(
            "**何のための設定？**\n\n"
            "Tripo3D が出した滑らかなメッシュを**何ブロック四方の解像度でボクセル化するか**を決めます。"
            "**1 voxel = 1 Minecraft ブロック** なので、これが直接「建物のブロック数」になります。\n\n"
            "計算式: `target_voxel = max(lower, min(upper, max(width, depth)))`\n"
            "（建物の縦／横の長い方を、lower〜upper の範囲にクランプ）\n\n"
            "**いつ触る？**\n"
            "- 🟦 出来高が**「1 ブロックが 10 倍に拡大されたドット絵」**になる → `voxel_lower_bound` を**下げる**（8〜12）\n"
            "- 🟪 出来高が**カクカクで細部が消える** → `voxel_lower_bound` を**上げる**（16〜20）\n"
            "- 🟫 巨大建築（50×50 など）で重い → `voxel_upper_bound` を下げる（32〜48）\n\n"
            "💡 **City Plan の 10×10 区画なら、下限 12 / 上限 48 で 1 voxel ≒ 1 ブロックの綺麗なマッピングになります。**",
            icon="🧱",
        )
        c1, c2 = st.columns(2)
        with c1:
            cfg.voxel_lower_bound = int(
                st.slider(
                    "voxel_lower_bound（最小解像度）",
                    min_value=8,
                    max_value=32,
                    value=int(cfg.voxel_lower_bound),
                    key="bnn_tripo_vlo",
                    help=(
                        "区画が小さくても保証されるボクセル数の下限。\n"
                        "小さくするほど concept art の 1 ブロックが Minecraft の 1 ブロックに近づく。\n"
                        "推奨: 12"
                    ),
                )
            )
            st.caption("⬇ 「ドット絵が拡大されすぎ」と感じたら下げる")
        with c2:
            cfg.voxel_upper_bound = int(
                st.slider(
                    "voxel_upper_bound（最大解像度）",
                    min_value=32,
                    max_value=128,
                    value=int(cfg.voxel_upper_bound),
                    key="bnn_tripo_vhi",
                    help=(
                        "大規模区画でもブロック数が無限大にならないよう抑える上限。\n"
                        "高くするほど大型建築のディテールが残る。\n"
                        "推奨: 48"
                    ),
                )
            )
            st.caption("⬆ 大型建築の細部が欲しいなら上げる")
        if cfg.voxel_lower_bound > cfg.voxel_upper_bound:
            st.warning(
                "voxel_lower_bound > voxel_upper_bound です。クランプ時に上限が優先されます。",
                icon="⚠️",
            )

    # --- Seed ------------------------------------------------------------
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
            cfg.model_seed = int(
                st.number_input(
                    "model_seed（形状の乱数）",
                    value=int(cfg.model_seed),
                    step=1,
                    key="bnn_tripo_mseed",
                    help=(
                        "メッシュ形状の生成シード。\n"
                        "同じ値 → 同じ形が再現される。値を変えると別パターンの 3D を引き直せる。"
                    ),
                )
            )
        with c2:
            cfg.texture_seed = int(
                st.number_input(
                    "texture_seed（テクスチャの乱数）",
                    value=int(cfg.texture_seed),
                    step=1,
                    key="bnn_tripo_tseed",
                    help=(
                        "テクスチャ生成側のシード。\n"
                        "形状はそのままに、色の塗り直しだけしたい時に変える。"
                    ),
                )
            )
        with c3:
            cfg.enable_image_autofix = st.checkbox(
                "enable_image_autofix（画像の自動補正）",
                value=bool(cfg.enable_image_autofix),
                key="bnn_tripo_autofix",
                help=(
                    "Tripo 側で入力画像を自動補正（背景除去、明るさ調整など）してから 3D 化する。\n"
                    "入力が Structure 画像（既にクリーンな白黒）なら不要。\n"
                    "コンセプトアートなど複雑な画像でうまく行かない時に ON にする実験用。"
                ),
            )

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
        if danger_button(
            "🔄 デフォルトに戻す",
            key="bnn_tripo_reset",
            confirm_title="Tripo 設定をデフォルトに戻しますか？",
            confirm_body=(
                "保存済みの `tripo_config.json` を削除し、推奨デフォルト値"
                "（style=voxel, voxel_lower_bound=12 など）にリセットします。"
            ),
            confirm_label="リセットする",
            use_container_width=True,
        ):
            st.session_state.tripo_config = reset_tripo_config()
            for k in list(st.session_state.keys()):
                if isinstance(k, str) and k.startswith("bnn_tripo_"):
                    st.session_state.pop(k, None)
            st.toast("Tripo 設定をリセットしました。", icon="🔄")
            st.rerun()


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
                        "style=voxel やボクセル解像度を調整して、画像の "
                        "1 ブロック ≒ Minecraft の 1 ブロックに揃えます。",
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
    _section_terraformer()
    st.divider()
    _section_project_management()


render()
