"""
City Planner - Gemini Function Calling client for Bananacraft 2.0 (Infrastructure Phase)

Analyzes the "Zoning Plan" (Building footprints) and generates instructions
to build roads, plazas, and terrain in the empty spaces.
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import asdict

try:
    from ai.providers.stage_client import complete_with_tools
    from ai.routing import AIStage
    from ai.key_store import apply_context
except ImportError:
    from app.ai.providers.stage_client import complete_with_tools
    from app.ai.routing import AIStage
    from app.ai.key_store import apply_context

# Import shared structures
try:
    from v2.architect import BuildingInstruction
except ImportError:
    from .architect import BuildingInstruction

# Infrastructure-specific Tools
INFRA_TOOLS = [
    {
        "name": "draw_road",
        "description": "Draws a road or path between two points.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "start": {"type": "ARRAY", "items": {"type": "INTEGER"}, "description": "[x, z] start coord"},
                "end": {"type": "ARRAY", "items": {"type": "INTEGER"}, "description": "[x, z] end coord"},
                "width": {"type": "INTEGER", "description": "Width of road in blocks (e.g. 3-5)"},
                "material": {"type": "STRING", "description": "Block ID (e.g. gravel, stone_bricks, dirt_path)"}
            },
            "required": ["start", "end", "width", "material"]
        }
    },
    {
        "name": "fill_zone",
        "description": "Fills a rectangular area with a material (for parks, plazas, water).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "x": {"type": "INTEGER", "description": "Top-left X"},
                "z": {"type": "INTEGER", "description": "Top-left Z"},
                "width": {"type": "INTEGER", "description": "Width"},
                "depth": {"type": "INTEGER", "description": "Depth"},
                "material": {"type": "STRING", "description": "Block ID (e.g. grass_block, water, sandstone)"},
                "decoration_type": {"type": "STRING", "description": "Optional theme: 'park', 'plaza', 'forest', 'none'"}
            },
            "required": ["x", "z", "width", "depth", "material"]
        }
    },
    {
        "name": "place_street_decor",
        "description": "Places a specific street decoration element.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "x": {"type": "INTEGER"},
                "z": {"type": "INTEGER"},
                "type": {"type": "STRING", "description": "Type: 'lantern_post', 'bench', 'fountain', 'tree', 'flower_bed'"}
            },
            "required": ["x", "z", "type"]
        }
    }
]

class CityPlanner:
    def __init__(self, api_key: Optional[str] = None):
        if api_key:
            apply_context({"GEMINI_API_KEY": api_key})

    @staticmethod
    def _to_instructions(results):
        return [BuildingInstruction(tool_name=r.name, parameters=r.arguments) for r in results]

    def generate_infrastructure(self, 
                                zoning_data: Dict[str, Any],
                                concept_text: str) -> List[BuildingInstruction]:
        """
        Generates road network and terrain fill instructions based on zoning.
        """
        buildings = zoning_data.get("buildings", [])
        
        # Prepare context
        building_summary = []
        for b in buildings:
            pos = b.get("position", {})
            building_summary.append({
                "id": b.get("id"),
                "type": b.get("type"),
                "rect": {
                    "x": pos.get("x"),
                    "z": pos.get("z"),
                    "w": pos.get("width"),
                    "d": pos.get("depth")
                }
            })

        system_prompt = """You are a Master City Planner for Minecraft.
Your task is to design the INFRASTRUCTURE (Roads, Plazas, Parks) for a new city.

CONTEXT:
- You are given a list of PLANNED BUILDINGS with their coordinates (200x200 grid).
- Your job is to FILL THE EMPTY SPACE.
- DO NOT build inside the building rectangles.

OBJECTIVES:
1. **Road Network**: simple, logical roads connecting major buildings.
   - Main roads (width 5-7) for landmarks.
   - Side roads (width 3) for smaller houses.
   - Use 'draw_road'.
   
2. **Terrain/Zones**: Fill large empty gaps.
   - 'fill_zone' with grass_block for nature/parks.
   - 'fill_zone' with stone_bricks/sandstone for plazas.
   
3. **Street Details**: Add life.
   - 'place_street_decor' for street lights (lantern_post) at corners.
   - Trees in park zones.

COORDINATES:
- X: 0-200, Z: 0-200.
- Y is handled by the builder (assumed ground level).

OUTPUT:
- Generate function calls to build the city floor plan.
"""

        user_prompt = f"""
# City Concept
{concept_text}

# Building Layout (Do not build here!)
{json.dumps(building_summary, indent=2)}

# Task
Design the roads and public spaces. 
1. Connect the buildings with a road network.
2. **CRITICAL: DO NOT BUILD ROADS ON TOP OF BUILDINGS!**
   - Check the `Building Layout` coordinates carefully.
   - Roads must go AROUND the building rectangles (leave 1-2 block gap).
   - If a building is at x=50, width=20 (ends x=70), the road cannot be between x=50 and x=70 at that z.
3. Fill remaining empty areas with parks or plazas suitable for the theme.
4. Add street lights and trees.
"""

        print("  🏗️ City Planner: Designing infrastructure...")
        results = complete_with_tools(
            AIStage.INFRASTRUCTURE,
            system=system_prompt,
            user_text=user_prompt,
            declarations=INFRA_TOOLS,
            image_bytes=None,
            temperature=0.4,
        )
        instructions = self._to_instructions(results)
        print(f"  🛣️ Generated {len(instructions)} infrastructure steps.")
        return instructions
