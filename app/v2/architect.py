"""
Architect - Gemini Function Calling client for Bananacraft 2.0

The Architect analyzes concept art and generates building instructions
using a 2-stage approach:
  Stage 1: Analyze image → Describe structure in JSON
  Stage 2: Generate tool calls from structure description
"""
import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

try:
    from ai.providers.stage_client import ToolCallResult, complete_json, complete_with_tools
    from ai.routing import AIStage
    from ai.key_store import apply_context
except ImportError:
    from app.ai.providers.stage_client import ToolCallResult, complete_json, complete_with_tools
    from app.ai.routing import AIStage
    from app.ai.key_store import apply_context


@dataclass
class BuildingInstruction:
    """Represents a single building operation from Gemini."""
    tool_name: str
    parameters: Dict[str, Any]
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Valid Minecraft block IDs for building
VALID_BLOCKS = [
    # Stone variants
    "stone", "stone_bricks", "mossy_stone_bricks", "cracked_stone_bricks",
    "cobblestone", "mossy_cobblestone", "andesite", "polished_andesite",
    "diorite", "polished_diorite", "granite", "polished_granite",
    "deepslate", "deepslate_bricks", "deepslate_tiles",
    # Bricks
    "bricks", "nether_bricks", "red_nether_bricks",
    # Sandstone
    "sandstone", "smooth_sandstone", "cut_sandstone",
    "red_sandstone", "smooth_red_sandstone",
    # Wood planks
    "oak_planks", "spruce_planks", "birch_planks", 
    "jungle_planks", "acacia_planks", "dark_oak_planks",
    "mangrove_planks", "cherry_planks",
    # Wood logs
    "oak_log", "spruce_log", "birch_log", "dark_oak_log",
    # Glass
    "glass", "white_stained_glass", "light_gray_stained_glass",
    "gray_stained_glass", "black_stained_glass", "light_blue_stained_glass",
    "blue_stained_glass", "cyan_stained_glass", "green_stained_glass",
    # Metals
    "iron_block", "gold_block", "copper_block", "iron_bars",
    # Concrete
    "white_concrete", "light_gray_concrete", "gray_concrete", "black_concrete",
    "brown_concrete", "red_concrete", "orange_concrete", "yellow_concrete",
    "lime_concrete", "green_concrete", "cyan_concrete", "light_blue_concrete",
    "blue_concrete", "purple_concrete", "magenta_concrete", "pink_concrete",
    # Terracotta
    "terracotta", "white_terracotta", "brown_terracotta", "red_terracotta",
    "orange_terracotta", "yellow_terracotta",
    # Quartz
    "quartz_block", "smooth_quartz", "quartz_bricks", "quartz_pillar",
    # Prismarine
    "prismarine", "prismarine_bricks", "dark_prismarine",
    # Other
    "obsidian", "crying_obsidian", "blackstone", "polished_blackstone",
    "end_stone", "end_stone_bricks", "purpur_block", "purpur_pillar",
    "sea_lantern", "glowstone", "shroomlight",
]


# Tool schemas with examples
TOOL_DECLARATIONS = [
    {
        "name": "draw_plane",
        "description": """Creates a filled quadrilateral surface between two edges.
Each edge is 2 points [x,y,z]. Use for walls, floors, or sloped roofs.
DO NOT add windows using this tool - use place_window instead.

Example - wall:
{
  "edge_a": [[0, 0, 0], [20, 0, 0]],
  "edge_b": [[0, 8, 0], [20, 8, 0]],
  "material": "bricks"
}

Example - sloped roof:
{
  "edge_a": [[0, 8, 0], [0, 8, 20]],
  "edge_b": [[10, 12, 0], [10, 12, 20]],
  "material": "dark_oak_planks"
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "edge_a": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                    "description": "First edge: [[x1,y1,z1], [x2,y2,z2]]"
                },
                "edge_b": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                    "description": "Second edge: [[x1,y1,z1], [x2,y2,z2]]"
                },
                "material": {
                    "type": "string",
                    "enum": VALID_BLOCKS,
                    "description": "Block type"
                }
            },
            "required": ["edge_a", "edge_b", "material"]
        }
    },
    {
        "name": "place_window",
        "description": """Places a window at a specified position on a wall.
Windows have glass, optional frame, and optional flower box.

Example - 2x2 window with oak frame and flowers:
{
  "position": [5, 3, 0],
  "width": 2,
  "height": 2,
  "facing": "north",
  "glass_type": "glass_pane",
  "frame_material": "oak_planks",
  "has_flower_box": true
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y, z] bottom-left of window"
                },
                "width": {"type": "integer", "description": "Width 1-5"},
                "height": {"type": "integer", "description": "Height 1-4"},
                "facing": {
                    "type": "string",
                    "enum": ["north", "south", "east", "west"]
                },
                "glass_type": {
                    "type": "string",
                    "enum": ["glass", "glass_pane", "white_stained_glass", "light_blue_stained_glass"]
                },
                "frame_material": {
                    "type": "string",
                    "enum": ["none", "oak_planks", "dark_oak_planks", "spruce_planks", "stone_bricks"]
                },
                "has_flower_box": {"type": "boolean"}
            },
            "required": ["position", "width", "height", "facing", "glass_type"]
        }
    },
    {
        "name": "place_door",
        "description": """Places a door at a specified position.
Doors can be single/double, with optional porch.

Example - double door with porch:
{
  "position": [8, 0, 0],
  "facing": "north",
  "door_type": "oak_door",
  "is_double": true,
  "has_porch": true,
  "porch_material": "oak_planks"
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y, z] bottom of door"
                },
                "facing": {
                    "type": "string",
                    "enum": ["north", "south", "east", "west"]
                },
                "door_type": {
                    "type": "string",
                    "enum": ["oak_door", "dark_oak_door", "spruce_door", "birch_door", "iron_door"]
                },
                "is_double": {"type": "boolean"},
                "has_porch": {"type": "boolean"},
                "porch_material": {
                    "type": "string",
                    "enum": ["oak_planks", "dark_oak_planks", "spruce_planks", "cobblestone"]
                }
            },
            "required": ["position", "facing", "door_type"]
        }
    },
    {
        "name": "place_decoration",
        "description": """Places decorative elements (lanterns, flowers, fences).

Example - lanterns at positions:
{
  "positions": [[5, 3, 0], [10, 3, 0]],
  "decoration_type": "lantern"
}

Example - fence line:
{
  "positions": [[0, 1, 5], [1, 1, 5], [2, 1, 5]],
  "decoration_type": "oak_fence"
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "positions": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                    "description": "List of [x, y, z]"
                },
                "decoration_type": {
                    "type": "string",
                    "enum": [
                        "lantern", "soul_lantern", "torch",
                        "oak_fence", "dark_oak_fence", "spruce_fence",
                        "potted_red_tulip", "potted_orange_tulip", "flower_pot",
                        "barrel", "chest", "white_banner", "red_banner"
                    ]
                }
            },
            "required": ["positions", "decoration_type"]
        }
    },
    {
        "name": "place_smart_pillar",
        "description": """Creates a vertical pillar/column.

Example:
{
  "base": [5, 0, 5],
  "top": [5, 15, 5],
  "material": "stone_bricks",
  "style": "classical"
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "base": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y, z] bottom"
                },
                "top": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y, z] top"
                },
                "material": {
                    "type": "string",
                    "enum": VALID_BLOCKS
                },
                "style": {
                    "type": "string",
                    "enum": ["simple", "classical", "modern"]
                }
            },
            "required": ["base", "top", "material"]
        }
    },
    {
        "name": "draw_curve_loft",
        "description": """Creates curved surface (arch, vault) between two curves.

Example - arched glass roof:
{
  "curve_a": {"start": [0, 10, 0], "end": [20, 10, 0], "control_height": 8},
  "curve_b": {"start": [0, 10, 30], "end": [20, 10, 30], "control_height": 8},
  "frame_material": "iron_block",
  "fill_material": "glass",
  "pattern": "grid_4x4"
}""",
        "parameters": {
            "type": "object",
            "properties": {
                "curve_a": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "array", "items": {"type": "integer"}},
                        "end": {"type": "array", "items": {"type": "integer"}},
                        "control_height": {"type": "integer"}
                    },
                    "required": ["start", "end", "control_height"]
                },
                "curve_b": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "array", "items": {"type": "integer"}},
                        "end": {"type": "array", "items": {"type": "integer"}},
                        "control_height": {"type": "integer"}
                    },
                    "required": ["start", "end", "control_height"]
                },
                "frame_material": {"type": "string", "enum": VALID_BLOCKS},
                "fill_material": {"type": "string", "enum": VALID_BLOCKS},
                "pattern": {"type": "string", "enum": ["solid", "grid_4x4", "grid_8x8"]}
            },
            "required": ["curve_a", "curve_b", "fill_material"]
        }
    }
]


class Architect:
    """
    The Architect - analyzes images and generates building instructions.
    
    Uses 2-stage generation:
      1. Analyze image → JSON structure description
      2. Generate tool calls from structure
    """
    
    def __init__(self, api_key: Optional[str] = None, debug: bool = False):
        if api_key:
            apply_context({"GEMINI_API_KEY": api_key})
        self.debug = debug

    @staticmethod
    def _tool_results_to_instructions(results: List[ToolCallResult]) -> List[BuildingInstruction]:
        return [BuildingInstruction(tool_name=r.name, parameters=r.arguments) for r in results]
    
    def analyze_structure(self, image_path: str, building_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage 1: Analyze the image and describe its structure.
        
        Returns a structured JSON describing the building components.
        """
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        width = building_info.get("position", {}).get("width", 50)
        depth = building_info.get("position", {}).get("depth", 50)
        
        system_prompt = f"""You are a building structure analyzer. Analyze the input image and describe the building's structure as JSON.

OUTPUT FORMAT:
{{
  "building_type": "station/house/tower/etc",
  "overall_dimensions": {{"width": X, "depth": Z, "height": Y}},
  "components": [
    {{
      "name": "component name (e.g., 'main hall', 'left wing', 'arched roof')",
      "type": "wall/floor/roof/pillar/arch",
      "position": {{"x_start": 0, "x_end": 20, "y_start": 0, "y_end": 10, "z_start": 0, "z_end": 30}},
      "material_suggestion": "bricks/stone/glass/etc",
      "has_windows": true/false,
      "roof_type": "flat/sloped/arched" (if applicable),
      "notes": "any special features"
    }}
  ],
  "spatial_relationships": [
    "left wing is attached to main hall at x=20",
    "arched roof spans from left to right above platform"
  ]
}}

BUILDING AREA: {width} x {depth} blocks
Be precise about positions. Identify ALL visible components including walls, floors, roofs, pillars."""

        user_prompt = "Analyze this building image and describe its structure as JSON."

        text = complete_json(
            AIStage.ARCHITECT_VISION,
            system=system_prompt,
            user=user_prompt,
            temperature=0.3,
            image_bytes=image_data,
            image_mime=self._get_mime_type(image_path),
        )
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except Exception:
            return {"raw_analysis": text, "error": "Could not parse as JSON"}
    
    def generate_from_structure(self, 
                                 structure: Dict[str, Any],
                                 building_info: Dict[str, Any]) -> List[BuildingInstruction]:
        """
        Stage 2: Generate tool calls from the structure description.
        """
        width = building_info.get("position", {}).get("width", 50)
        depth = building_info.get("position", {}).get("depth", 50)
        
        system_prompt = f"""You are a Minecraft architect. Generate building tool calls to FAITHFULLY recreate the structure from the description.

COORDINATE SYSTEM:
- X: 0 to {width}, Z: 0 to {depth}, Y: 0 = ground
- All values are integers

AVAILABLE TOOLS:
1. draw_plane - For walls, floors, AND SLOPED ROOFS
2. place_window - Windows with glass, frames, and flower boxes
3. place_door - Doors (single/double) with optional porch
4. place_decoration - Lanterns, fences, flowers
5. place_smart_pillar - Vertical columns
6. draw_curve_loft - Arched roofs (curved)

CRITICAL - SLOPED ROOF CONSTRUCTION:
To create a sloped/pitched roof, edge_a and edge_b must have DIFFERENT Y values!
- edge_a = bottom edge of roof (lower Y)
- edge_b = ridge/peak of roof (higher Y)

EXAMPLE - Pitched roof (left slope):
{{
  "edge_a": [[0, 8, 0], [0, 8, 20]],   <- y=8 at wall edge
  "edge_b": [[10, 12, 0], [10, 12, 20]], <- y=12 at ridge (center)
  "material": "bricks"
}}

EXAMPLE - Pitched roof (right slope):
{{
  "edge_a": [[10, 12, 0], [10, 12, 20]], <- ridge
  "edge_b": [[20, 8, 0], [20, 8, 20]],   <- wall edge
  "material": "bricks"
}}

For a complete gable roof, you need TWO sloped planes meeting at the ridge!

RULES:
- Use draw_plane with different Y values for sloped roofs
- The roof MUST have a slope - not flat boxes!
- Add windows using place_window
- Add doors using place_door
- Add decorations (lanterns, flower pots, fences)

Generate ALL tool calls. Do NOT create flat/box roofs for houses!"""

        facing = building_info.get("facing", "unknown")
        user_prompt = f"""Generate tool calls to build this structure:

{json.dumps(structure, indent=2, ensure_ascii=False)}

CONTEXT:
This building faces **{facing.upper()}**.
- The FACADE facing {facing} should be the GRANDEST / MOST DETAILED.
- The entrance should be on the {facing} side.
- Back side can be simpler.

IMPORTANT: Create a proper SLOPED ROOF using draw_plane with different Y coordinates!
For gable roof: create two sloped planes from walls up to central ridge.

Create EVERY component:
- Walls (stone/wood as described)
- SLOPED ROOF (not flat!) - edge_a lower, edge_b at ridge
- Windows with frames and flower boxes
- Door with porch (on {facing} side)
- Decorations (lanterns, fences, etc.)"""

        results = complete_with_tools(
            AIStage.ARCHITECT_BUILD,
            system=system_prompt,
            user_text=user_prompt,
            declarations=TOOL_DECLARATIONS,
            image_bytes=None,
            temperature=0.5,
        )
        return self._tool_results_to_instructions(results)
    
    def analyze_and_plan(self, 
                         image_path: str,
                         building_info: Dict[str, Any],
                         additional_context: str = "") -> List[BuildingInstruction]:
        """
        2-stage generation: analyze structure then generate tools.
        """
        # Stage 1: Analyze structure
        print("  📐 Stage 1: Analyzing structure...")
        structure = self.analyze_structure(image_path, building_info)
        
        if "error" in structure:
            print(f"  ⚠️ Analysis warning: {structure.get('error')}")
        else:
            print(f"  ✅ Found {len(structure.get('components', []))} components")
        
        # Stage 2: Generate tool calls
        print("  🔨 Stage 2: Generating tool calls...")
        instructions = self.generate_from_structure(structure, building_info)
        
        return instructions
    
    def analyze_and_plan_with_debug(self, 
                                    image_path: str,
                                    building_info: Dict[str, Any]) -> tuple:
        """
        2-stage generation with debug information.
        
        Returns:
            (instructions, debug_info) where debug_info contains all prompts and responses
        """
        debug_info = {}
        
        # Load image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        width = building_info.get("position", {}).get("width", 50)
        depth = building_info.get("position", {}).get("depth", 50)
        
        # Stage 1: Analyze structure
        print("  📐 Stage 1: Analyzing structure...")
        
        stage1_system = f"""You are a Minecraft building analyzer. Analyze the input image and describe EVERY visible element as JSON.

OUTPUT FORMAT:
{{
  "building_type": "house/station/tower/etc",
  "overall_dimensions": {{"width": X, "depth": Z, "height": Y}},
  "components": [
    {{
      "name": "component name",
      "type": "wall/floor/roof/pillar/window/door/decoration",
      "position": {{"x_start": 0, "x_end": 20, "y_start": 0, "y_end": 10, "z_start": 0, "z_end": 30}},
      "material": "dark_oak_planks/stone_bricks/bricks/etc",
      "details": {{
        "window_count": 2,
        "window_size": "2x2",
        "has_flower_box": true,
        "door_type": "single/double",
        "decoration_type": "lantern/fence/etc"
      }}
    }}
  ],
  "windows": [
    {{"position": [x, y, z], "width": 2, "height": 2, "facing": "north", "has_frame": true, "has_flower_box": true}}
  ],
  "doors": [
    {{"position": [x, y, z], "facing": "north", "is_double": false, "has_porch": true}}
  ],
  "decorations": [
    {{"type": "lantern", "positions": [[x, y, z], [x2, y2, z2]]}}
  ]
}}

BUILDING AREA: {width} x {depth} blocks

IMPORTANT: Identify EVERY visible element including:
- Walls (material, position, any exposed log frames)
- Windows (exact positions, sizes, frames, flower boxes)
- Doors (position, type, porch)
- Roofs (type: flat/sloped/arched, material)
- Decorations (lanterns, flower pots, fences, banners)
- Structural elements (pillars, log beams)

Count and position each window and door precisely!"""

        stage1_user = "Analyze this Minecraft building image. Identify and position EVERY element: walls, windows, doors, roof, decorations, structural elements."
        
        debug_info["stage1_system_prompt"] = stage1_system
        debug_info["stage1_user_prompt"] = stage1_user
        
        stage1_response_text = complete_json(
            AIStage.ARCHITECT_VISION,
            system=stage1_system,
            user=stage1_user,
            temperature=0.3,
            image_bytes=image_data,
            image_mime=self._get_mime_type(image_path),
        )
        debug_info["stage1_response"] = stage1_response_text
        
        # Parse structure
        try:
            text = stage1_response_text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            structure = json.loads(text.strip())
        except Exception:
            structure = {"raw_analysis": stage1_response_text, "error": "Could not parse as JSON"}
        
        if "error" in structure:
            print(f"  ⚠️ Analysis warning: {structure.get('error')}")
        else:
            print(f"  ✅ Found {len(structure.get('components', []))} components")
        
        # Stage 2: Generate tool calls
        print("  🔨 Stage 2: Generating tool calls...")
        
        stage2_system = f"""You are a Minecraft architect. Generate building tool calls to FAITHFULLY recreate the structure.

COORDINATE SYSTEM:
- X: 0 to {width}, Z: 0 to {depth}, Y: 0 = ground
- All values are integers

AVAILABLE TOOLS:
1. draw_plane - For walls, floors, AND SLOPED ROOFS
2. place_window - Windows with glass, frames, and flower boxes
3. place_door - Doors (single/double) with optional porch
4. place_decoration - Lanterns, fences, flowers
5. place_smart_pillar - Vertical columns
6. draw_curve_loft - Arched roofs (curved)

CRITICAL - SLOPED ROOF CONSTRUCTION:
To create a sloped/pitched roof, edge_a and edge_b must have DIFFERENT Y values!
- edge_a = bottom edge of roof (lower Y)
- edge_b = ridge/peak of roof (higher Y)

EXAMPLE - Pitched roof (left slope):
{{
  "edge_a": [[0, 8, 0], [0, 8, 20]],   <- y=8 at wall edge
  "edge_b": [[10, 12, 0], [10, 12, 20]], <- y=12 at ridge (center)
  "material": "bricks"
}}

EXAMPLE - Pitched roof (right slope):
{{
  "edge_a": [[10, 12, 0], [10, 12, 20]], <- ridge
  "edge_b": [[20, 8, 0], [20, 8, 20]],   <- wall edge
  "material": "bricks"
}}

For a complete gable roof, you need TWO sloped planes meeting at the ridge!

RULES:
- Use draw_plane with different Y values for sloped roofs
- The roof MUST have a slope - not flat boxes!
- Add windows using place_window
- Add doors using place_door
- Add decorations (lanterns, flower pots, fences)

Generate ALL tool calls. Do NOT create flat/box roofs for houses!

CRITICAL - GROUNDING RULE:
All vertical structures (walls, pillars) MUST start at Y=0 (Ground Level).
Do NOT create floating structures. If a wall or pillar exists, it must extend down to Y=0."""

        stage2_user = f"""Generate tool calls to build this structure:

{json.dumps(structure, indent=2, ensure_ascii=False)}

IMPORTANT: Create a proper SLOPED ROOF using draw_plane with different Y coordinates!
For gable roof: create two sloped planes from walls up to central ridge.

Create EVERY component:
- Walls (stone/wood as described)
- SLOPED ROOF (not flat!) - edge_a lower, edge_b at ridge
- Windows with frames and flower boxes
- Door with porch
- Decorations (lanterns, fences, etc.)"""

        debug_info["stage2_system_prompt"] = stage2_system
        debug_info["stage2_user_prompt"] = stage2_user
        
        tool_results = complete_with_tools(
            AIStage.ARCHITECT_BUILD,
            system=stage2_system,
            user_text=stage2_user,
            declarations=TOOL_DECLARATIONS,
            image_bytes=None,
            temperature=0.5,
        )
        instructions = self._tool_results_to_instructions(tool_results)
        debug_info["stage2_function_calls"] = [
            {"tool": i.tool_name, "parameters": i.parameters} for i in instructions
        ]
        
        return instructions, debug_info
    
    def analyze_and_plan_single_stage(self, 
                                      image_path: str,
                                      building_info: Dict[str, Any]) -> List[BuildingInstruction]:
        """
        Original single-stage generation (fallback).
        """
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        width = building_info.get("position", {}).get("width", 50)
        depth = building_info.get("position", {}).get("depth", 50)
        
        system_prompt = f"""You are a Minecraft architect. Recreate the building in the image using voxels.

COORDINATES: X: 0-{width}, Z: 0-{depth}, Y: 0=ground

TOOLS:
- draw_plane: walls, floors, roofs (any flat surface)
- place_smart_pillar: columns
- draw_curve_loft: arched roofs

Generate ALL tool calls to faithfully recreate the structure."""

        user_prompt = f"Recreate this building. Area: {width}x{depth} blocks."
        
        results = complete_with_tools(
            AIStage.ARCHITECT_BUILD,
            system=system_prompt,
            user_text=user_prompt,
            declarations=TOOL_DECLARATIONS,
            image_bytes=image_data,
            image_mime=self._get_mime_type(image_path),
            temperature=0.7,
        )
        
        return self._tool_results_to_instructions(results)
    
    def _get_mime_type(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")
    
    def generate_from_description(self, 
                                  description: str,
                                  building_info: Dict[str, Any]) -> List[BuildingInstruction]:
        """Generate from text description."""
        width = building_info.get("position", {}).get("width", 50)
        depth = building_info.get("position", {}).get("depth", 50)
        
        system_prompt = f"""Minecraft architect. Area: {width}x{depth}, Y=0 ground.
Tools: draw_plane (surfaces), place_smart_pillar (columns), draw_curve_loft (arches)."""

        user_prompt = f"Build: {description}"
        
        results = complete_with_tools(
            AIStage.ARCHITECT_BUILD,
            system=system_prompt,
            user_text=user_prompt,
            declarations=TOOL_DECLARATIONS,
            image_bytes=None,
            temperature=0.7,
        )
        
        return self._tool_results_to_instructions(results)
