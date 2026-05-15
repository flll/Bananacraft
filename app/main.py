import streamlit as st
import time
import pandas as pd
import altair as alt
import json
import os
import requests
import base64
from dotenv import load_dotenv
load_dotenv()

# Fix path for imports when running via Streamlit from root
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from api_client import GeminiClient
from ai.routing import AIStage, Provider, effective_route
from meshy_client import MeshyClient
# Legacy voxelizer import commented out
# from voxelizer import Voxelizer

# New BVH Ray-Cast Voxelizer
from voxelizer.mesh_loader import load_mesh
from voxelizer.bvh_ray_voxelizer import voxelize_mesh
from voxelizer.block_assigner import BlockAssigner
import plotly.graph_objects as go
import pandas as pd
from file_manager import FileManager 
from rcon_client import RconClient
from terraformer import Terraformer 

# v2 Imports
from v2.architect import Architect
from v2.carpenter import CarpenterSession
from v2.decorator import Decorator
from v2.preview import create_3d_preview 
from v2.city_planner import CityPlanner
from v2.blueprint_analyzer import BlueprintAnalyzer

from ai.key_store import apply_context
from ai.browser_keys import load_persisted_keys, save_persisted_keys, clear_persisted_keys
from ai.routing import AIStage, resolve_api_key_for_stage

# --- Page Configuration ---
st.set_page_config(
    page_title="Bananacraft Architect",
    page_icon="🍌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .stButton>button { color: #0E1117; background-color: #F63366; border: none; font-weight: bold; }
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# --- Authentication ---
def check_password():
    """Returns `True` if the user had a correct password."""

    # 1. No password set in env -> Allow
    password = os.getenv("STREAMLIT_PASSWORD")
    if not password:
        return True

    # 2. Check session state
    if st.session_state.get("password_correct", False):
        return True

    # 3. Show Input
    st.write("# 🔒 Login Required")
    input_password = st.text_input("Password", type="password", key="password_input")
    
    if st.button("Login"):
        if input_password == password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 Password incorrect")
            
    return False

if not check_password():
    st.stop()  # Stop execution if not authenticated

# --- Session State Initialization ---
if 'phase' not in st.session_state:
    st.session_state.phase = 0 # 0 = Project Setup
if 'project_name' not in st.session_state:
    st.session_state.project_name = ""
if 'architect' not in st.session_state:
    st.session_state.architect = None
if 'carpenter_session' not in st.session_state:
    st.session_state.carpenter_session = None
if 'file_manager' not in st.session_state:
    st.session_state.file_manager = None
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = None
if 'chat_session' not in st.session_state:
    st.session_state.chat_session = None

if 'concept' not in st.session_state:
    st.session_state.concept = None # {title, description, image_bytes}
if 'zoning' not in st.session_state:
    st.session_state.zoning = None
if 'selected_zone' not in st.session_state:
    st.session_state.selected_zone = None
# For Design Phase
if 'design_images' not in st.session_state:
    st.session_state.design_images = None

if "api_key_context" not in st.session_state:
    st.session_state.api_key_context = {}
if not st.session_state.get("_browser_keys_hydrated"):
    st.session_state.api_key_context.update(load_persisted_keys())
    st.session_state._browser_keys_hydrated = True
with st.sidebar:
    st.title("🍌 Bananacraft")
    st.caption("AI都市開発システム")

    with st.expander("🔑 API キー（session / localStorage）", expanded=False):
        st.caption(
            "localStorage に保存できます。XSS のあるページではキーが漏洩しうるため、"
            "信頼できる環境でのみ利用し、本番ではサーバ側シークレットやプロキシを推奨します。"
        )
        if "sb_gem" not in st.session_state and st.session_state.api_key_context.get("GEMINI_API_KEY"):
            st.session_state.sb_gem = st.session_state.api_key_context["GEMINI_API_KEY"]
        if "sb_oai" not in st.session_state and st.session_state.api_key_context.get("OPENAI_API_KEY"):
            st.session_state.sb_oai = st.session_state.api_key_context["OPENAI_API_KEY"]
        if "sb_ant" not in st.session_state and st.session_state.api_key_context.get("ANTHROPIC_API_KEY"):
            st.session_state.sb_ant = st.session_state.api_key_context["ANTHROPIC_API_KEY"]

        st.text_input("GEMINI_API_KEY", type="password", key="sb_gem", help="画像生成・フォールバック用")
        st.text_input("OPENAI_API_KEY", type="password", key="sb_oai", help="区画 JSON・建築 FC 等")
        st.text_input("ANTHROPIC_API_KEY", type="password", key="sb_ant", help="コンセプト対話・装飾 FC 等")

        for wkey, env in (
            ("sb_gem", "GEMINI_API_KEY"),
            ("sb_oai", "OPENAI_API_KEY"),
            ("sb_ant", "ANTHROPIC_API_KEY"),
        ):
            v = st.session_state.get(wkey, "")
            if isinstance(v, str) and v.strip():
                st.session_state.api_key_context[env] = v.strip()

        apply_context(st.session_state.api_key_context)
        for k, v in st.session_state.api_key_context.items():
            if v:
                os.environ[k] = v

        c_save, c_clr = st.columns(2)
        with c_save:
            if st.button("ブラウザに保存", help="localStorage に書き込み"):
                try:
                    save_persisted_keys(st.session_state.api_key_context)
                    st.success("保存しました")
                except Exception as e:
                    st.warning(str(e))
        with c_clr:
            if st.button("ブラウザから削除", type="secondary"):
                clear_persisted_keys()
                st.session_state.api_key_context = {}
                for wkey in ("sb_gem", "sb_oai", "sb_ant"):
                    st.session_state.pop(wkey, None)
                st.session_state._browser_keys_hydrated = False
                apply_context({})
                st.rerun()

    st.divider()
    if st.session_state.phase > 0:
        st.info(f"Project: {st.session_state.project_name}")
        
        # --- World Settings (Global) ---
        st.subheader("🌍 World Settings")
        fm = st.session_state.file_manager
        
        # Check config
        config_path = "project_config.json"
        project_config = {}
        if fm and fm.exists(config_path):
            project_config = fm.load_json(config_path)
        
        saved_origin = project_config.get("origin", {"x": 0, "y": 64, "z": 0})
        
        st.caption("建設予定地の原点(南西)")
        origin_x = st.number_input("Origin X", value=saved_origin['x'])
        origin_y = st.number_input("Origin Y", value=saved_origin['y'])
        origin_z = st.number_input("Origin Z", value=saved_origin['z'])
        
        # Save automatically or via implicit state update? 
        # Better to have a save button or just use session state persistence if strictly needed.
        # For simplicity, we save when button clicked.
        if st.button("Save Origin"):
             if fm:
                 project_config["origin"] = {"x": origin_x, "y": origin_y, "z": origin_z}
                 fm.save_json(config_path, project_config)
                 st.success("Saved!")
        
        st.divider()
        
        # --- Terraforming (Moved to Sidebar) ---
        st.subheader("🚜 Terraformer")
        st.caption(f"Area: ({origin_x}, {origin_z}) to ({origin_x+200}, {origin_z+200})")
        
        if st.button("Run Terraformer (Clear 200x200)"):
             try:
                 with st.spinner("Clearing area & Fixing chunks..."):
                     # Connect to RCON
                     rcon = RconClient()
                     terra = Terraformer(rcon)
                     
                     # Use the *current* input values, not just saved ones, 
                     # but typically we should use saved. 
                     # Let's use the input values from st.number_input above to be responsive.
                     
                     target_origin = (int(origin_x), int(origin_y), int(origin_z))
                     
                     logs = terra.terraform(target_origin, width=200, depth=200, base_y=target_origin[1])
                     st.success("Terraforming Complete!")
                     with st.expander("Logs"):
                         st.write(logs)
             except Exception as e:
                 st.error(f"Terraforming Failed: {e}")
        
        st.divider()
        
        if st.button("プロジェクトを閉じる"):
            st.session_state.clear()
            st.rerun()

# --- Phase 0: Project Setup ---
if st.session_state.phase == 0:
    st.title("Welcome to Bananacraft")
    st.markdown("新しい都市開発プロジェクトを開始します。")
    
    with st.form("project_init"):
        p_name = st.text_input("プロジェクト名 (半角英数推奨)", placeholder="Neo_Tokyo_2077")
        submitted = st.form_submit_button("プロジェクト作成")
        
        if submitted and p_name:
            # Init Managers
            try:
                try:
                    resolve_api_key_for_stage(AIStage.IMAGE_RENDER)
                except ValueError:
                    st.error(
                        "API キーが不足しています。サイドバーの GEMINI_API_KEY（画像生成）を設定するか、"
                        ".env に GEMINI_API_KEY を設定してください。"
                    )
                    st.stop()

                st.session_state.project_name = p_name
                st.session_state.file_manager = FileManager(p_name)
                st.session_state.gemini_client = GeminiClient()
                st.session_state.chat_session = st.session_state.gemini_client.start_chat()

                # Initializing v2 Architect
                try:
                    st.session_state.architect = Architect()
                except Exception as e:
                    st.error(f"Failed to initialize Architect: {e}")

                
                # Persistence Check
                fm = st.session_state.file_manager
                if fm.exists("concept_art.jpg") and fm.exists("concept_prompt_refined.txt") and fm.exists("concept_reasoning.txt"):
                    st.toast("Existing project data found. Loading...", icon="📂")
                    st.session_state.concept = {
                        "title": "Concept Art",
                        "description": fm.load_text("concept_reasoning.txt"),
                        "refined_prompt": fm.load_text("concept_prompt_refined.txt"),
                        "image_path": os.path.join(fm.project_dir, "concept_art.jpg")
                    }
                
                # Dynamic Zoning Adjustment Support
                if fm.exists("zoning_adjusted.json"):
                    st.session_state.zoning = fm.load_json("zoning_adjusted.json")
                    st.toast("Loaded Adjusted Zoning Plan", icon="📏")
                elif fm.exists("zoning_data.json"):
                    st.session_state.zoning = fm.load_json("zoning_data.json")

                st.session_state.phase = 1
                st.rerun()
            except Exception as e:
                st.error(f"初期化エラー: {e}")

# --- Phase 1: Concept & Zoning ---
elif st.session_state.phase == 1:
    st.title("Planning Phase: コンセプト & 区画整理")
    fm = st.session_state.file_manager
    client = st.session_state.gemini_client
    
    # 1. Concept Definition
    if not st.session_state.concept:
        prompt = st.text_area("街のコンセプトを入力", height=150, placeholder="例：魔法使いが住むかっこいいお城")
        if st.button("コンセプト生成"):
            if prompt:
                _cr = effective_route(AIStage.CONCEPT_BRAIN)
                _spin = (
                    "Gemini でコンセプトを洗練しています..."
                    if _cr.provider == Provider.GOOGLE
                    else (
                        "Claude でコンセプトを洗練しています..."
                        if _cr.provider == Provider.ANTHROPIC
                        else "OpenAI でコンセプトを洗練しています..."
                    )
                )
                with st.spinner(_spin):
                    # 1. Refine Prompt (Text Interaction)
                    # Returns dict: {"reasoning": "...", "image_prompt": "..."}
                    try:
                        refined_data = client.refine_prompt(prompt)
                        reasoning = refined_data.get("reasoning", "No reasoning provided.")
                        img_prompt = refined_data.get("image_prompt", prompt)
                    except Exception as e:
                        st.error(f"Refinement Error: {e}")
                        st.stop()
                    
                    st.write(f"Thinking Process: {reasoning}")

                with st.spinner("Nano Banana Pro is painting..."):
                    # 2. Image Generation with refined prompt
                    img_bytes = client.generate_image(img_prompt)
                    
                    if img_bytes:
                        # Save Artifacts
                        fm.save_text("concept_input.txt", prompt)
                        fm.save_text("concept_reasoning.txt", reasoning)
                        fm.save_text("concept_prompt_refined.txt", img_prompt)
                        img_path = fm.save_image("concept_art.jpg", img_bytes)
                        
                        st.session_state.concept = {
                            "title": "Concept Art", 
                            "description": reasoning,
                            "refined_prompt": img_prompt,
                            "image_path": img_path
                        }
                        st.rerun()
                    else:
                        st.error("画像生成に失敗しました。")

    else:
        # Display & Feedback
        c1, c2 = st.columns([2, 1])
        with c1:
            st.image(st.session_state.concept['image_path'], caption="Generated Concept")
            with st.expander("Geminiの思考プロセス (Detail)", expanded=True):
                st.write(st.session_state.concept['description'])
            with st.expander("生成プロンプト (Internal)", expanded=False):
                st.code(st.session_state.concept['refined_prompt'])
        
        with c2:
            st.subheader("Feedback Loop")
            feedback = st.text_area("修正指示", placeholder="例：もっと不気味にして。夜にして。")
            if st.button("修正案を再生成"):
                with st.spinner("Refining based on feedback..."):
                    # Context is maintained in chat_session
                    try:
                        refined_data = client.refine_prompt(f"修正指示: {feedback}")
                        reasoning = refined_data.get("reasoning", "")
                        img_prompt = refined_data.get("image_prompt", "")
                    except Exception as e:
                        st.error(f"Refinement Error: {e}")
                        st.stop()

                    with st.spinner("Repainting..."):
                        new_img_bytes = client.generate_image(img_prompt)
                        
                        if new_img_bytes:
                            timestamp = fm._get_timestamp()
                            fm.save_text(f"concept_feedback_{timestamp}.txt", feedback)
                            fm.save_text(f"concept_reasoning_{timestamp}.txt", reasoning)
                            fm.save_text(f"concept_prompt_{timestamp}.txt", img_prompt)
                            new_img_path = fm.save_image(f"concept_art_{timestamp}.jpg", new_img_bytes)
                            
                            st.session_state.concept['description'] = reasoning
                            st.session_state.concept['refined_prompt'] = img_prompt
                            st.session_state.concept['image_path'] = new_img_path
                            st.rerun()

            st.divider()
            if not st.session_state.zoning:
                if st.button("✅ コンセプト承認 -> 区画整理へ"):
                    with st.spinner("Generating Zoning Data..."):
                        try:
                            ctx_parts = []
                            c = st.session_state.concept or {}
                            if c.get("description"):
                                ctx_parts.append("【コンセプト思考】\n" + str(c["description"]))
                            if c.get("refined_prompt"):
                                ctx_parts.append("【画像生成プロンプト】\n" + str(c["refined_prompt"]))
                            if fm.exists("concept_input.txt"):
                                cin = fm.load_text("concept_input.txt")
                                if cin:
                                    ctx_parts.append("【ユーザー初期入力】\n" + cin)
                            concept_ctx = "\n\n".join(ctx_parts)
                            zoning_data = client.generate_zoning_json(concept_ctx)
                            # The client now returns parsed object or list
                            # Apply Fixes (Collision Resolution & Orientation)
                            from v2.zoning_fixer import fix_zoning
                            zoning_data = fix_zoning(zoning_data)
                            st.session_state.zoning = zoning_data
                            fm.save_json("zoning_data.json", zoning_data)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Zoning Generation Error: {e}")

    # 2. Zoning Visualization
    if st.session_state.zoning:
        st.divider()
        st.subheader(f"Zoning Map: {st.session_state.zoning.get('theme', 'Urban Plan')}")
        
        zoning_data = st.session_state.zoning
        buildings = zoning_data.get("buildings", [])

        if not buildings:
            st.warning("No building data found in zoning JSON.")
        else:
            # Matplotlib Visualization
            import matplotlib.pyplot as plt
            import matplotlib.patches as patches
            import matplotlib.colors as mcolors

            # Create figure
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.set_xlim(0, 200)
            ax.set_ylim(200, 0) # 0 at Top-Left (Map style)
            ax.set_aspect('equal')
            ax.set_xlabel("X Block")
            ax.set_ylabel("Z Block")
            ax.grid(True, linestyle='--', alpha=0.3)
            ax.set_title("City Layout Plan (200x200)")

            # Draw Frame
            frame = patches.Rectangle((0, 0), 200, 200, linewidth=2, edgecolor='black', facecolor='#f0f2f6')
            ax.add_patch(frame)

            # 1. Visualize Infrastructure (Roads/Zones)
            infra_file = "infrastructure.json"
            if fm.exists(infra_file):
                infra_data = fm.load_json(infra_file)
                for item in infra_data:
                    tool = item.get("tool_name", "")
                    params = item.get("parameters", {})
                    
                    if tool == "draw_road":
                        start = params.get("start", [0, 0])
                        end = params.get("end", [0, 0])
                        width = params.get("width", 3)
                        # Draw Line
                        ax.plot([start[0], end[0]], [start[1], end[1]], color='gray', linewidth=width, alpha=0.6, solid_capstyle='round')
                        
                    elif tool == "fill_zone":
                        zx = params.get("x", 0)
                        zz = params.get("z", 0)
                        zw = params.get("width", 1)
                        zd = params.get("depth", 1)
                        mat = params.get("material", "grass")
                        c = "green" if "grass" in mat else "lightgray"
                        rect = patches.Rectangle((zx, zz), zw, zd, linewidth=0, facecolor=c, alpha=0.3)
                        ax.add_patch(rect)

            colors = list(mcolors.TABLEAU_COLORS.values())

            # 2. Visualize Buildings
            for i, b in enumerate(buildings):
                pos = b.get("position", {})
                x = pos.get("x", 0)
                z = pos.get("z", 0)
                w = pos.get("width", 10)
                d = pos.get("depth", 10)
                
                b_name = b.get("name", "Unknown")
                b_type = b.get("type", "normal")
                
                # Check for overlap or out of bounds (Visual only)
                color = "gold" if b_type == "landmark" else colors[i % len(colors)]
                
                rect = patches.Rectangle((x, z), w, d, linewidth=1, edgecolor='black', facecolor=color, alpha=0.7)
                ax.add_patch(rect)
                
                # Add text label
                ax.text(x + w/2, z + d/2, str(i+1), fontsize=10, ha='center', va='center', color='white', fontweight='bold')

            st.pyplot(fig)
            
            # --- Infrastructure Controls ---
            st.divider()
            st.subheader("Phase 1.5: Infrastructure")
            ic1, ic2 = st.columns(2)
            
            with ic1:
                if st.button("🛣️ Generate City Infrastructure"):
                    with st.spinner("City Planner is designing roads & parks..."):
                        try:
                            planner = CityPlanner() # Uses env API Key
                            concept_text = st.session_state.concept.get('description', '')
                            infra_plan = planner.generate_infrastructure(zoning_data, concept_text)
                            
                            # Convert to dicts for JSON
                            infra_json = [i.to_dict() for i in infra_plan]
                            fm.save_json("infrastructure.json", infra_json)
                            st.success(f"Infrastructure Plan Generatored ({len(infra_json)} steps)!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Planning Error: {e}")

            with ic2:
                if fm.exists("infrastructure.json"):
                    if st.button("🚜 Construct Infrastructure (RCON)"):
                        with st.spinner("Terraforming..."):
                            try:
                                # Load plan
                                plan = fm.load_json("infrastructure.json")
                                # Convert tool names back if needed, but build_from_json handles 'tool_name'
                                rcon_ip = os.getenv("RCON_HOST", "localhost")
                                rcon_port = int(os.getenv("RCON_PORT", 28889))
                                rcon_pass = os.getenv("RCON_PASSWORD", "")
                                
                                # Use Carpenter directly via Session or Function
                                # Need RconClient
                                # The current 'build_from_json' in carpenter sends commands? 
                                # No, 'Carpenter.build' returns Block dicts. 
                                # We need RconClient to send them.
                                
                                # Load Project Config for Origin
                                config_path = "project_config.json"
                                origin_setting = {"x": 0, "y": 64, "z": 0}
                                if fm.exists(config_path):
                                    cfg = fm.load_json(config_path)
                                    origin_setting = cfg.get("origin", origin_setting)
                                
                                ox = origin_setting['x']
                                oy = origin_setting['y']
                                oz = origin_setting['z']
                                
                                st.info(f"Building Infrastructure at Origin: ({ox}, {oy}, {oz})")

                                # Initialize Session
                                session = CarpenterSession(origin=(ox, oy, oz)) 
                                blocks_to_place = session.build_from_json(plan)
                                
                                # Send via RCON
                                rcon = RconClient()
                                logs = rcon.build_voxels(blocks_to_place, origin=(0, 0, 0))
                                st.success(f"Infrastructure Built! ({len(blocks_to_place)} blocks)")
                                
                            except Exception as e:
                                st.error(f"Construction Error: {e}")
            
            st.divider()
            
            # Legacy Altair removed for clarity as requested

        # Selection Interface
        st.write("### Building List")
        
        # Display as cards or list
        cols = st.columns(3)
        for i, b in enumerate(buildings):
            with cols[i % 3]:
                with st.container(border=True):
                    # Thumbnail
                    thumb_file = f"design_{b['id']}_decorated.jpg"
                    if fm.exists(thumb_file):
                        st.image(os.path.join(fm.project_dir, thumb_file), use_container_width=True)
                    else:
                        st.info("No Design", icon="⬜")
                        
                    st.markdown(f"**{i+1}. {b['name']}**")
                    st.caption(f"{b['type']} | ({b['position']['x']}, {b['position']['z']})")
                    if st.button(f"Design This", key=f"btn_{i}"):
                        st.session_state.selected_zone = b
                        st.session_state.phase = 2
                        st.session_state.design_images = None
                        st.rerun()

# --- Phase 2: Design ---
elif st.session_state.phase == 2:
    st.title("Phase 2: Building Design")
    zone = st.session_state.selected_zone
    st.markdown(f"**Target Zone**: {zone['name']} ({zone['type']})")
    
    client = st.session_state.gemini_client
    fm = st.session_state.file_manager
    
    # Attempt to restore design images from disk if not in session
    if not st.session_state.design_images:
        dec_filename = f"design_{zone['id']}_decorated.jpg"
        str_filename = f"design_{zone['id']}_structure.jpg"
        
        # Check if files exist
        if fm.exists(dec_filename):
            # We need absolute paths for st.image
            dec_path = os.path.join(fm.project_dir, dec_filename)
            str_path = None
            
            if fm.exists(str_filename):
                str_path = os.path.join(fm.project_dir, str_filename)
                
            st.session_state.design_images = {
                "decorated": dec_path,
                "structure": str_path
            }
            # Rerun to update UI with loaded images
            st.rerun()
    
    col_in, col_view = st.columns([1, 2])
    
    with col_in:
        design_prompt = st.text_area("デザインプロンプト", value=f"{zone.get('description')} architecture, detailed")
        if st.button("Generate Designs"):
            with st.spinner("Generating Dual Images (Concept & Structure)..."):
                try:
                    if st.session_state.concept and 'image_path' in st.session_state.concept:
                        # Re-read the file bytes
                        try:
                            with open(st.session_state.concept['image_path'], "rb") as f:
                                concept_image_bytes = f.read()
                        except Exception as e:
                            print(f"Warning: Could not read concept art for reference: {e}")

                    # 1. Generate Concept (Decorated) First
                    width = zone.get('position', {}).get('width', 10)
                    depth = zone.get('position', {}).get('depth', 10)
                    
                    dec_bytes = client.generate_concept_image(design_prompt, width, depth, concept_image_bytes)
                    
                    if dec_bytes:
                        p_path = fm.save_image(f"design_{zone['id']}_decorated.jpg", dec_bytes)
                        # Store in session state immediately to show progress
                        st.session_state.design_images = {
                            "decorated": p_path,
                            "structure": None 
                        }
                        # Force a rerun to render the decorated image before starting the heavy structure gen
                        # BUT, rerun stops execution. We need a way to continue.
                        # Simplest way in Streamlit is to use st.image directly here for immediate feedback, 
                        # or use a placeholder.
                        
                        placeholder = st.empty()
                        with placeholder.container():
                            st.success("Concept Image Generated!")
                            st.image(p_path, caption="Concept Art (Decorated)")
                        
                        # 2. Generate Structure
                        with st.spinner("Generating Structure Image (Removing Decorations)..."):
                            str_bytes = client.generate_structure_image(dec_bytes)
                            
                            if str_bytes:
                                s_path = fm.save_image(f"design_{zone['id']}_structure.jpg", str_bytes)
                                st.session_state.design_images["structure"] = s_path
                                st.rerun()
                            else:
                                st.error("Structure generation failed.")
                    else:
                        st.error("Concept generation failed.")
                except Exception as e:
                    st.error(f"Generation Error: {e}")
        
        if st.session_state.design_images:
            feedback = st.text_area("修正指示 (Design)")
            if st.button("デザイン修正"):
                with st.spinner("Regenerating..."):
                    # Simplified regen for prototype
                    new_dec = client.generate_image(f"{design_prompt}, {feedback}, detailed")
                    if new_dec:
                        ts = fm._get_timestamp()
                        p_path = fm.save_image(f"design_{zone['id']}_dec_{ts}.jpg", new_dec)
                        st.session_state.design_images['decorated'] = p_path
                        st.rerun()

            st.markdown("---")
            # Legacy Mock button removed

    with col_view:
        if st.session_state.design_images:
            t1, t2 = st.tabs(["✨ Concept", "🏗️ Structure"])
            
            with t1: 
                if st.session_state.design_images.get('decorated'):
                    st.image(st.session_state.design_images['decorated'])
            
            with t2: 
                if st.session_state.design_images.get('structure'):
                    st.image(st.session_state.design_images['structure'])
                else:
                    st.info("Generating Structure...")

            if st.session_state.design_images and st.session_state.design_images.get('structure'):
                st.markdown("---")
                st.subheader("Architectural Planning (Gemini 3)")
                
                # Check for existing instruction
                inst_file = f"building_{zone['id']}_instructions.json"
                if fm.exists(inst_file):
                    try:
                        instructions = fm.load_json(inst_file)
                        st.success("Architectural Blueprint Found!")
                        st.json(instructions, expanded=False)
                    except Exception as e:
                        st.warning(f"Corrupted blueprint found, resetting: {e}")
                        instructions = None
                    
                    if st.button("Regenerate Blueprint"):
                         instructions = None # Force regen logic below

                else:
                    instructions = None

                if not instructions:
                    if st.button("Create Blueprint (Analyze Structure)"):
                         arc = st.session_state.architect
                         if not arc:
                             st.error("Architect not initialized.")
                         else:
                             with st.spinner("Gemini 3 is analyzing the structure..."):
                                 # Prepare building info
                                 b_info = {
                                     "name": zone['name'],
                                     "width": zone['position']['width'],
                                     "depth": zone['position']['depth'],
                                     "description": zone.get('description', '')
                                 }
                                 # Local path
                                 s_path = st.session_state.design_images['structure']
                                 
                                 try:
                                     # Stage 1: Analyze
                                     analysis = arc.analyze_structure(s_path, b_info)
                                     
                                     # Stage 2: Plan (Generate Instructions)
                                     instructions_list = arc.generate_from_structure(analysis, b_info)
                                     
                                     # Convert to serializable format
                                     instructions = [i.to_dict() for i in instructions_list]
                                     
                                     # Debug: Show analysis
                                     with st.expander("Debug: Gemini Analysis"):
                                         st.json(analysis)
                                         st.write("Generated Instructions count:", len(instructions))
                                     
                                     # Save
                                     fm.save_json(inst_file, instructions)
                                     st.success("Blueprint Created!")
                                     st.rerun()
                                 except Exception as e:
                                     st.error(f"Planning Error: {e}")

                if instructions:
                    st.markdown("---")
                    st.subheader("Construction Planning (Carpenter)")
                    
                    # Check for existing blocks
                    blocks_file = f"building_{zone['id']}_blocks_v2.json"
                    blocks = []
                    
                    if fm.exists(blocks_file):
                         blocks = fm.load_json(blocks_file)
                         st.success(f"Construction Data Ready: {len(blocks)} blocks")
                         
                    if not blocks:
                        if st.button("Generate Construction Data"):
                            try:
                                with st.spinner("Carpenter is calculating block placements..."):
                                    # Init Carpenter
                                    carpenter = CarpenterSession()
                                    
                                    # Build
                                    blocks = carpenter.build_from_json(instructions)
                                    
                                    # Save
                                    fm.save_json(blocks_file, blocks)
                                    
                                    # --- Dynamic Zoning Adjustment ---
                                    # FIX: Import path must be relative to execution root
                                    try:
                                        from app.v2.layout_engine import LayoutEngine
                                    except ImportError:
                                        # Fallback if running directly inside app/
                                        from v2.layout_engine import LayoutEngine
                                    
                                    # Load current source of truth for zoning
                                    current_zoning = []
                                    if fm.exists("zoning_adjusted.json"):
                                        current_zoning = fm.load_json("zoning_adjusted.json")
                                    elif fm.exists("zoning_data.json"):
                                        current_zoning = fm.load_json("zoning_data.json")
                                    
                                    if current_zoning:
                                        engine = LayoutEngine(current_zoning)
                                        # Update dimensions
                                        updated = engine.update_zone_from_blocks(zone['id'], blocks)
                                        if updated:
                                            # Resolve collisions (shift coordinates if needed)
                                            moved = engine.resolve_collisions(zone['id'])
                                            
                                            # Save adjusted plan
                                            new_zoning = engine.get_zones()
                                            fm.save_json("zoning_adjusted.json", new_zoning)
                                            st.session_state.zoning = new_zoning # Update state
                                            
                                            msg = "Construction Data Generated."
                                            if moved:
                                                msg += " (Zone Adjusted to avoid collision!)"
                                            st.success(msg)
                                    else:
                                        st.success(f"Construction Complete! Generated {len(blocks)} blocks.")
                                        
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Construction Error: {e}")
                                st.error(f"Construction Error: {e}")
                    
                    # Preview Section
                    if blocks:
                         st.markdown("### 3D Preview")
                         fig = create_3d_preview(blocks, title=f"{zone['name']} (Preview)")
                         st.plotly_chart(fig, use_container_width=True)
                         
                         if st.button("Proceed to Site (Phase 3)"):
                             st.session_state.phase = 3
                             st.rerun()

# --- Phase 3: Construction ---
# --- Phase 3: Construction & Integration ---
elif st.session_state.phase == 3:
    st.header("Phase 3: Construction & Integration")
    fm = st.session_state.file_manager
    zone = st.session_state.selected_zone
    
    # 1. World Settings
    project_config = {}
    if fm.exists("project_config.json"):
        project_config = fm.load_json("project_config.json")
    saved_origin = project_config.get("origin", {'x':0, 'y':64, 'z':0})
    current_origin = (saved_origin['x'], saved_origin['y'], saved_origin['z'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Structure Build")
        st.info("Deploy the blueprint to the Minecraft Server.")
        
        # Load Zoning Data to get Offset
        zoning_offset = (zone['position']['x'], zone['position']['z'])
        st.caption(f"Building: {zone['name']} (Offset: {zoning_offset})")
        
        # Final Absolute Coordinate
        abs_x = current_origin[0] + zoning_offset[0]
        abs_y = 0 # Y is already calculated in blocks (default 64)
        abs_z = current_origin[2] + zoning_offset[1]
        
        build_origin = (abs_x, abs_y, abs_z)
        st.markdown(f"**Build Location**: `{build_origin}`")
        
        # Update: Look for v2 blocks file
        v2_blocks_file = f"building_{zone['id']}_blocks_v2.json"
        
        if fm.exists(v2_blocks_file):
            if st.button("🚀 Instant Build (Structure)"):
                try:
                    with st.spinner(f"Building at {build_origin}..."):
                        rcon = RconClient()
                        blocks = fm.load_json(v2_blocks_file)
                        
                        # Fix: Force persistent leaves for structure execution
                        for b in blocks:
                            b_type = b['type']
                            if "leaves" in b_type:
                                if "persistent=true" not in b_type:
                                    if "[" in b_type:
                                        b["type"] = b_type.replace("]", ",persistent=true]")
                                    else:
                                        b["type"] = b_type + "[persistent=true]"
                        
                        # Build at absolute location
                        # blocks_v2 already has relative coordinates (x, y, z)
                        # rcon.build_voxels adds origin to them
                        log = rcon.build_voxels(blocks, origin=build_origin)
                        
                        st.success(f"Build Command Sent! ({len(blocks)} blocks)")
                        with st.expander("Server Response Log"):
                             st.write(log)
                except Exception as e:
                    st.error(f"Build Failed: {e}")
            
            # --- Reset / Clear Function ---
            st.markdown("---")
            if st.button("🗑️ Clear Area (Reset)", help="Fills the building area with air (Above ground only)."):
                try:
                    with st.spinner("Clearing area (Calculated from Structure)..."):
                        rcon = RconClient()
                        
                        # 1. Try to get bounds from actual blocks
                        # v2_blocks_file is defined above
                        
                        final_x1, final_y1, final_z1 = 0, 0, 0
                        final_x2, final_y2, final_z2 = 0, 0, 0
                        
                        if fm.exists(v2_blocks_file):
                            blocks = fm.load_json(v2_blocks_file)
                            if blocks:
                                # blocks are relative to build_origin (which has Y=0 usually)
                                # but the blocks inside have Y=64 etc.
                                
                                # Calculate relative min/max
                                xs = [b['x'] for b in blocks]
                                ys = [b['y'] for b in blocks]
                                zs = [b['z'] for b in blocks]
                                
                                min_rx, max_rx = min(xs), max(xs)
                                min_ry, max_ry = min(ys), max(ys)
                                min_rz, max_rz = min(zs), max(zs)
                                
                                # Apply build_origin offset
                                # FIX: Reverting previous change. Blocks ARE relative.
                                # user confirmed "363, 64..." was correct area, but volume was issue.
                                # So we MUST add ox, oy, oz.
                                
                                ox, oy, oz = build_origin
                                
                                # FIX: Y-Alignment.
                                # blocks_v2 have Y ~ 64. build_origin has Y=0. Result = 64.
                                # But if user World Origin Y is 100, building is at 100.
                                # We MUST use current_origin[1] as base.
                                
                                final_x1 = ox + min_rx - 2
                                final_z1 = oz + min_rz - 2
                                
                                # Use User's Y, plus building height
                                # Assume building starts at base.
                                height = max_ry - min_ry
                                final_y1 = current_origin[1] 
                                final_y2 = final_y1 + height + 5
                                
                                final_x2 = ox + max_rx + 2
                                final_z2 = oz + max_rz + 2
                                
                                st.info(f"Detected Structure Bounds: {final_x1},{final_y1},{final_z1} to {final_x2},{final_y2},{final_z2}")
                            else:
                                # Empty blocks file? Fallback
                                final_x1 = build_origin[0]
                                final_y1 = current_origin[1]
                                final_z1 = build_origin[2]
                                final_x2 = final_x1 + zone['position']['width']
                                final_y2 = final_y1 + 100
                                final_z2 = final_z1 + zone['position']['depth']
                        else:
                            # Fallback to Zoning
                            final_x1 = build_origin[0]
                            final_y1 = current_origin[1]
                            final_z1 = build_origin[2]
                            final_x2 = final_x1 + zone['position']['width']
                            final_y2 = final_y1 + 100
                            final_z2 = final_z1 + zone['position']['depth']
                            
                        st.warning(f"Target Area: {final_x1},{final_y1},{final_z1} to {final_x2},{final_y2},{final_z2}")
                        
                        # Chunking to avoid volume limit (32768 blocks)
                        # Area = (x2-x1) * (z2-z1) * h
                        # We slice by Height (Y)
                        
                        y_start = final_y1
                        y_end = final_y2
                        # FIX: chunk_height of 10 means 11 layers inclusive (y to y+10).
                        # Area 55x55 = 3025 blocks. 3025 * 11 = 33275 > 32768 limit!
                        # So we must reduce height. 
                        # 32768 / 3025 = 10.8. Max 10 layers safe.
                        # chunk_height = 8 means 9 layers (y to y+8). Safe.
                        chunk_height = 8
                        
                        cmds = []
                        while y_start < y_end:
                            y_chunk_end = min(y_start + chunk_height, y_end)
                            # Ensure we don't exceed y_end
                            
                            cmd = f"fill {final_x1} {y_start} {final_z1} {final_x2} {y_chunk_end} {final_z2} air"
                            cmds.append(cmd)
                            y_start = y_chunk_end + 1 # Move to next layer? fill is inclusive.
                            # if chunk is 64 to 74. Next should be 75.
                            # fill x1 y1 z1 x2 y2 z2 replaces inclusive.
                            
                            # Wait, logic above:
                            # y_start = 64. y_chunk_end = 74. 
                            # fill ... 64 ... 74 ...
                            # next y_start should be 75. 
                            y_start = y_chunk_end + 1
                        
                        st.info(f"Splitting into {len(cmds)} commands to fit volume limits.")
                        
                        # Fix: Ensure chunks are loaded!
                        # Use forceload
                        fl_add = f"forceload add {final_x1} {final_z1} {final_x2} {final_z2}"
                        fl_remove = f"forceload remove {final_x1} {final_z1} {final_x2} {final_z2}"
                        
                        full_cmds = [fl_add] + cmds + [fl_remove]
                        
                        log = rcon.connect_and_send(full_cmds)
                        
                        st.success(f"Area Cleared!")
                        with st.expander("Detailed RCON Logs"):
                            for l in log:
                                st.text(l)
                        
                except Exception as e:
                    st.error(f"Clear Failed: {e}")
        else:
            st.warning(f"No blueprint found ({v2_blocks_file}). Please complete Phase 2.")
            if st.button("Back to Phase 2"):
                st.session_state.phase = 2
                st.rerun()

    with col2:
        st.subheader("3. AI Decoration (Bot)")
        
        # Initialize session state for decoration if needed
        if 'decoration_status' not in st.session_state:
            st.session_state.decoration_status = None
            
        # A. Analyze & Plan
        if st.button("🎨 Generate Decoration Plan"):
            with st.spinner("Gemini is analyzing structure & concept..."):
                try:
                    # Uses globally imported Decorator
                    dec = Decorator() # Uses env API key
                    
                    # Context
                    concept = zone.get('description', '')
                    if fm.exists("concept_reasoning.txt"):
                        concept += "\n" + fm.load_text("concept_reasoning.txt")
                        
                    # Structure Instructions (for context)
                    inst_file = f"building_{zone['id']}_instructions.json"
                    instructions_data = []
                    if fm.exists(inst_file):
                        instructions_data = fm.load_json(inst_file) # dicts
                    
                    # Image (Target)
                    image_path = None
                    # Try finding the best image
                    possible_images = [
                        st.session_state.design_images.get('decorated'),
                        f"projects/{st.session_state.project_name}/design_1_decorated.jpg",
                         "design_1_decorated.jpg"
                    ]
                    for img in possible_images:
                        if img and os.path.exists(img):
                            image_path = img
                            break
                    
                    if not image_path:
                        st.error("No decorated design image found!")
                    else:
                        st.info(f"Using design: {os.path.basename(image_path)}")
                        
                        # Reconstruct building info
                        b_info = {
                             "name": zone['name'],
                             "width": zone['position']['width'],
                             "depth": zone['position']['depth'],
                             "description": zone.get('description', '')
                        }

                        # Check for existing decoration plan
                        deco_file = f"building_{zone['id']}_decoration.json"
                        deco_instructions_list = []
                        
                        # Generate new (Always regen on button click or load existing?)
                        # Button says "Generate", so we force regen or at least load logic
                        
                        # Load actual blocks for accurate placement
                        blocks_file = f"building_{zone['id']}_blocks_v2.json"
                        structure_blocks = []
                        if fm.exists(blocks_file):
                             raw_blocks = fm.load_json(blocks_file)
                             if raw_blocks:
                                 min_y = min(b['y'] for b in raw_blocks)
                                 # Shift everyone down
                                 structure_blocks = [
                                     {**b, 'y': b['y'] - min_y} 
                                     for b in raw_blocks
                                 ]
                        else:
                             st.warning(f"No block data found ({blocks_file}). Using instructions fallback.")
                             structure_blocks = []

                        # Generate new
                        deco_instructions_objects = dec.generate_decoration_plan(
                             image_path=image_path,
                             concept_text=concept,
                             structure_instructions=instructions_data,
                             building_info=b_info
                        )
                        if deco_instructions_objects:
                             deco_instructions_list = [i.to_dict() for i in deco_instructions_objects]
                             fm.save_json(deco_file, deco_instructions_list)
                             st.session_state.decoration_status = "Generated"
                             st.success(f"Decoration Plan Generated! ({len(deco_instructions_list)} steps)")
                        else:
                             st.error("Failed to generate decoration instructions.")

                except Exception as e:
                    st.error(f"Decoration Planning Failed: {e}")

        # B. Execution (Manual -> Bot)
        # Check if file exists to show the button (Persistent state)
        deco_file_check = f"building_{zone['id']}_decoration.json"
        
        if fm.exists(deco_file_check):
            st.divider()
            st.subheader("B. Execute Decoration")
            
            # Use columns for layout
            dc1, dc2 = st.columns([1, 1])
            with dc1:
                st.info("Decoration Plan Available")
                if st.button("View Plan JSON"):
                    st.json(fm.load_json(deco_file_check), expanded=False)

            with dc2:
                if st.button("👷 Run AI Carpenter (Auto)"):
                     try:
                        with st.spinner("AI Carpenter is working... (This may take a minute)"):
                            # Use CarpenterSession to run bot
                            cs = CarpenterSession()
                            
                            # Calculate origin again or retrieve
                            # build_origin should be in scope? No, it was calculated in col1.
                            # We need to recalculate it or grab from session/config.
                            # But wait, phase 2 doesn't blindly have 'build_origin'.
                            # It relies on 'saved_origin' global.
                            
                            # Re-read global config
                            config_path_g = "project_config.json"
                            p_conf = {}
                            if fm.exists(config_path_g):
                                p_conf = fm.load_json(config_path_g)
                            saved_origin_g = p_conf.get("origin", {"x": 0, "y": 64, "z": 0})
                            
                            # Zone position
                            z_ox = zone['position']['x']
                            z_oz = zone['position']['z']
                            
                            # BUT wait, did we shift the zone in `LayoutEngine`? 
                            # 'zone' variable comes from st.session_state.selected_zone.
                            # Is selected_zone updated when zoning.json updates?
                            # Not automatically unless we re-select it or refresh 'st.session_state.zoning'.
                            # We should re-fetch the latest zone data to be safe.
                            
                            # Refetch zone
                            # `st.session_state.zoning` might be a dict (zoning_adjusted) or list (zoning_data legacy)
                            zoning_source = st.session_state.zoning
                            if isinstance(zoning_source, dict):
                                zoning_source = zoning_source.get('buildings', [])
                                
                            latest_zone = next((z for z in zoning_source if z['id'] == zone['id']), zone)
                            z_ox = latest_zone['position']['x']
                            z_oz = latest_zone['position']['z']
                            
                            current_origin = (saved_origin_g['x'], saved_origin_g['y'], saved_origin_g['z'])
                            build_origin = (
                                current_origin[0] + z_ox,
                                current_origin[1], # Y is usually flat
                                current_origin[2] + z_oz
                            )
                            
                            # Convert plan to bot instructions first!
                            # The logic to convert to raw blocks was inside the button before.
                            # We need to ensure decoration.json (bot format) exists.
                            
                            # 1. Load Plan
                            deco_plan = fm.load_json(deco_file_check)
                            
                            # 2. Convert to Blocks
                            carpenter_temp = CarpenterSession(origin=(0,0,0))
                            # We need structure instructions for context? Analyzer needs them?
                            # Analyzer uses them to find walls etc.
                            inst_file_Temp = f"building_{zone['id']}_instructions.json"
                            inst_data_temp = []
                            if fm.exists(inst_file_Temp):
                                inst_data_temp = fm.load_json(inst_file_Temp)
                                
                            analyzer_temp = BlueprintAnalyzer(inst_data_temp)
                            deco_blocks = carpenter_temp.build_from_json(deco_plan, analyzer=analyzer_temp)
                            
                            # 3. Format for Bot
                            bot_instructions = []
                            for b in deco_blocks:
                                 block_type = b['type']
                                 if "leaves" in block_type and "persistent=true" not in block_type:
                                     if "[" in block_type:
                                         block_type = block_type.replace("]", ",persistent=true]")
                                     else:
                                         block_type += "[persistent=true]"
                                 bot_instructions.append({
                                     "x": b['x'], "y": b['y'], "z": b['z'],
                                     "action": "setblock", "block": block_type
                                 })
                            
                            # 4. Save decoration.json (Target for bot)
                            # Bot script expects "decoration.json"? 
                            # The previous code used `target_file=target_file_name`. MAKE SURE names match.
                            # Previous code: `target_file_name = f"building_{zone['id']}_decoration.json"`
                            # BUT `fm.save_json("decoration.json", ...)` was used inside.
                             
                            # Actually, `run_bot` takes `target_file`. 
                            # If we save to `temp_bot_instructions.json`, we pass that.
                            bot_target_file = f"bot_instructions_{zone['id']}.json"
                            fm.save_json(bot_target_file, {"instructions": bot_instructions})
                            
                            result_log = cs.run_bot(
                                project_name=st.session_state.project_name, 
                                target_file=bot_target_file,
                                origin=build_origin
                            )
                            
                            st.success("Decoration Complete!")
                            st.session_state.decoration_status = "Executed"
                            with st.expander("Carpenter Bot Logs"):
                                st.code(result_log)
                                
                     except Exception as e:
                        st.error(f"Bot Execution Failed: {e}")
        
        # Show Plan if exists
        if fm.exists("decoration.json"):
            plan = fm.load_json("decoration.json")
            # plan['instructions'] is the list
            count = len(plan.get('instructions', []))
            st.caption(f"Ready to deploy {count} blocks via Bot.")
            
            # B. Deploy Bot (Mock / Future)
            if st.button("Merge & Build (Structure + Decoration)"):
                 st.info("Merging decoration into final build...")
                 try:
                     # 1. Structure Blocks
                     carpenter = CarpenterSession(origin=(0, 0, 0))
                     # Re-load structure instructions
                     inst_file = f"building_{zone['id']}_instructions.json"
                     structure_blocks = []
                     if fm.exists(inst_file):
                         inst_data = fm.load_json(inst_file)
                         structure_blocks = carpenter.build_from_json(inst_data)
                     
                     # 2. Decoration Blocks
                     # plan['instructions'] is already in Bot format ({x,y,z,block,action})
                     # We need to parse them back or just append. 
                     # Structure blocks from carpenter are dicts {x,y,z,type,properties...}
                     # We need to convert structure blocks to Bot format first.
                     
                     final_instructions = []
                     
                     # Add Structure
                     for b in structure_blocks:
                         b_type = b['type']
                         # Force persistent leaves for structure too
                         if "leaves" in b_type:
                             if "persistent=true" not in b_type:
                                 if "[" in b_type:
                                     b_type = b_type.replace("]", ",persistent=true]")
                                 else:
                                     b_type += "[persistent=true]"
                                     
                         final_instructions.append({
                             "x": b['x'],
                             "y": b['y'],
                             "z": b['z'],
                             "action": "setblock",
                             "block": b_type
                         })
                         
                     # Add Decoration (Resolve instructions -> blocks first)
                     # Load Analyzer context for accurate placement
                     inst_file_dec = f"building_{zone['id']}_instructions.json"
                     inst_data_dec = []
                     if fm.exists(inst_file_dec):
                         inst_data_dec = fm.load_json(inst_file_dec)
                     analyzer_dec = BlueprintAnalyzer(inst_data_dec)
                     
                     # Resolve to blocks
                     deco_blocks = carpenter.build_from_json(plan, analyzer=analyzer_dec)
                     
                     for b in deco_blocks:
                         b_type = b['type']
                         # Force persistent leaves for decoration
                         if "leaves" in b_type:
                             if "persistent=true" not in b_type:
                                 if "[" in b_type:
                                     b_type = b_type.replace("]", ",persistent=true]")
                                 else:
                                     b_type += "[persistent=true]"
                                     
                         final_instructions.append({
                             "x": b['x'],
                             "y": b['y'],
                             "z": b['z'],
                             "action": "setblock",
                             "block": b_type
                         })
                     
                     # Save
                     final_file = "full_build.json"
                     fm.save_json(final_file, {"instructions": final_instructions})
                     
                     st.success(f"Merged Build Ready! Total blocks: {len(final_instructions)}")
                     
                     # 3. Instant Build (RCON Optimized)
                     if st.checkbox("Execute Instant Build (RCON)", value=True):
                         with st.spinner(f"Building {len(final_instructions)} blocks via RCON..."):
                             # Convert to format expected by build_voxels ({x,y,z,type})
                             # Our final_instructions are {x,y,z,block,action}
                             rcon_blocks = []
                             for inst in final_instructions:
                                 rcon_blocks.append({
                                     'x': inst['x'],
                                     'y': inst['y'],
                                     'z': inst['z'],
                                     'type': inst['block'] # build_voxels expects 'type'
                                 })
                             
                             # Calculate Absolute Origin
                             abs_origin = (
                                 current_origin[0] + zone['position']['x'],
                                 current_origin[1],
                                 current_origin[2] + zone['position']['z']
                             )
                             
                             rcon = RconClient()
                             logs = rcon.build_voxels(rcon_blocks, origin=abs_origin)
                             st.success(f"Build Complete! Sent {len(logs)} commands.")

                     # Fallback Command
                     project_id = st.session_state.project_name
                     abs_x = current_origin[0] + zone['position']['x']
                     abs_y = current_origin[1]
                     abs_z = current_origin[2] + zone['position']['z']
                     
                     cmd = f"node AI_Carpenter_Bot/index.js {project_id} {abs_x} {abs_y} {abs_z} full_build.json"
                     with st.expander("Show Bot Command (Fallback)"):
                         st.code(cmd, language="bash")
                         st.info("Use this if RCON fails or for animation.")
                     
                 except Exception as e:
                     st.error(f"Merge & Build Failed: {e}")
            
            if st.button("🤖 Summon Carpenter Bot (Decoration Only)"):
                st.info("Summoning Bot...")
                project_id = st.session_state.project_name
                
                # Pass origin
                abs_x = current_origin[0] + zone['position']['x']
                abs_y = current_origin[1]
                abs_z = current_origin[2] + zone['position']['z']
                
                cmd = f"node AI_Carpenter_Bot/index.js {project_id} {abs_x} {abs_y} {abs_z} decoration.json"
                st.code(cmd, language="bash")
                st.warning("Run this to build DECORATION ONLY.")

    st.divider()
    if st.button("⬅️ Back to Building List"):
        st.session_state.phase = 1
        st.rerun()

    if st.button("Restart Project"):
        st.session_state.clear()
        st.rerun()
