"""
Decorator - Gemini Function Calling client for Bananacraft 2.0 (Decoration Phase)
Updated for "Set Generation" approach using Target IDs.
"""
import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import asdict

try:
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    from ai.routing import AIStage, client_for_stage, text_model
except ImportError:
    from app.ai.routing import AIStage, client_for_stage, text_model

from .architect import BuildingInstruction
from .blueprint_analyzer import BlueprintAnalyzer

# New Tool Declaration for Decorator
DECORATOR_TOOLS = [
    {
        "name": "decorate_element",
        "description": "Attaches a custom structure (decoration set) to a target architectural element (Wall, Window, etc).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target_id": {"type": "INTEGER", "description": "ID of the element to decorate"},
                "position": {
                    "type": "STRING", 
                    "enum": ["bottom_left", "bottom_center", "center", "top_center"],
                    "description": "Anchor point on the target"
                },
                "offset": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                    "description": "[x, y, z] Offset from anchor (Local Coords). Z is depth."
                },
                "structures": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "x": {"type": "INTEGER"},
                            "y": {"type": "INTEGER"},
                            "z": {"type": "INTEGER"},
                            "type": {"type": "STRING"}
                        },
                        "required": ["x", "y", "z", "type"]
                    },
                    "description": "List of blocks relative to anchor. Local Z=0 is Surface, Z=1 is Protruding."
                }
            },
            "required": ["target_id", "structures"]
        }
    }
]

class Decorator:
    def __init__(self, api_key: Optional[str] = None):
        if not HAS_GENAI:
            raise ImportError("google-genai package required")
        
        self._key_override = api_key
        self.client = client_for_stage(AIStage.DECORATION, api_key)
        self.model_name = text_model(AIStage.DECORATION) 

    def _get_mime_type(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")

    def _parse_response(self, response) -> List[BuildingInstruction]:
        instructions = []
        if not response.candidates: return []
        for candidate in response.candidates:
            if not candidate.content or not candidate.content.parts: continue
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    params = dict(fc.args) if fc.args else {}
                    instructions.append(BuildingInstruction(tool_name=fc.name, parameters=params))
        return instructions

    def generate_decoration_plan(self, 
                                 image_path: str,
                                 concept_text: str,
                                 structure_instructions: List[Dict],
                                 building_info: Dict[str, Any]) -> List[BuildingInstruction]:
        """
        Generates decoration instructions based on Semantic Anchors.
        """
        # 1. Analyze the existing structure to get ID Map
        analyzer = BlueprintAnalyzer(structure_instructions)
        element_summary = analyzer.get_element_summary()
        
        # Load Image
        image_data = None
        if image_path and os.path.exists(image_path):
             with open(image_path, "rb") as f:
                image_data = f.read()

        system_prompt = f"""You are a Master Facade Designer for Minecraft.
Your task is to RENOVATE a basic building structure into a high-detail masterpiece matching the Concept Image.

**METHODOLOGY: ANCHORED SET GENERATION**
Do not place random blocks. Instead, attach "Decoration Sets" to existing architectural elements (Walls, Windows).

**INPUT DATA:**
You are provided with a list of **TARGETABLE ELEMENTS** (IDs) derived from the structure blueprint.
- ID: 0 | Type: WALL ...
- ID: 1 | Type: WINDOW ...

**YOUR TOOL: `decorate_element`**
Use this to paint blocks onto a target.
- **Coordinate System (Local)**:
    - **X, Y**: Horizontal / Vertical relative to the target's face.
    - **Z**: DEPTH. 
        - **Z = 0**: The Surface of the wall/window. (Replaces existing block)
        - **Z = 1**: One block PROTRUDING OUT (Attached to wall).
        - **Z = -1**: One block INSIDE (Recessed).

**STRATEGY: "ONE-STROKE" PAINTING**
If the Architect made a boring wall (ID: 5), but the image shows a fancy window with a balcony:
1. Target ID: 5 (Wall).
2. Define a `structure` list that contains EVERYTHING:
   - The Glass blocks (at Z=0, replacing the wall).
   - The Frame (at Z=1).
   - The Flower Box (at Z=1, Y=-1).
   - The Leaves hanging down (at Z=1, Y=-2).

**STYLE GUIDELINES:**
1. **DEPTH IS KING**: Never build flat. Always add blocks at Z=1 (Trapdoors, Stairs, Fences).
2. **ORGANIC CHAOS**: Don't just place 1 flower. Place a grass block, a trapdoor, a flower, and a hanging vine.
3. **SUPPORT STRUCTURES**: If you add a balcony, add supports (fences) underneath it.
4. **NO FLOATING BLOCKS**: If you add a lantern, attach it to a fence or block.

**TASK:**
Look at the Concept Image. Identify the key features (Awnings, Planters, Shutters, Balconies).
Apply them to the corresponding Element IDs in the list.

**CRITICAL RULES:**
1. **RESPECT DIMENSIONS**: The list below provides the Size (WxH) for each element.
   - You MUST NOT place blocks outside these dimensions (local X and Y).
   - If a wall is 5x5, do not place a block at x=6 or y=6. It will hang in the air or clip into neighbors.
2. **NO FLOATING BLOCKS**: Do not assume there is a wall where there isn't one. Only attach to the given IDs.
3. **CENTERING**: Use `position="center"` for windows/doors to ensure accurate placement.
"""

        user_prompt = f"""
# Concept Theme
{concept_text}

# Targetable Elements (Structure Map)
{element_summary}

# Task
Apply decorations to these IDs to match the image style.
If a wall (ID) is empty but needs a window, DRAW THE WINDOW AND THE DECORATION on it using `decorate_element`.
"""
        
        contents = []
        if image_data:
            contents.append(types.Part.from_bytes(data=image_data, mime_type=self._get_mime_type(image_path)))
        contents.append(user_prompt)
        
        tool_config = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=tool["parameters"]
                )
                for tool in DECORATOR_TOOLS
            ]
        )

        print("  🎨 Decorator: Planning attached decorations...")
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[tool_config],
                temperature=0.5,
            )
        )
        
        return self._parse_response(response)