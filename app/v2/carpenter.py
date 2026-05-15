"""
Carpenter - Tool execution engine for Bananacraft 2.0
Updated to support Context Injection (BlueprintAnalyzer)
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .tools import TOOL_REGISTRY
from .tools.base import Block
from .architect import BuildingInstruction
# Late import to avoid circular dep if needed, or assume present
# from .blueprint_analyzer import BlueprintAnalyzer (Passed as object usually)


@dataclass
class BuildResult:
    success: bool
    blocks: List[Block]
    tool_name: str
    message: str = ""


class Carpenter:
    def __init__(self, origin: tuple = (0, 64, 0), analyzer=None):
        self.origin = origin
        self.analyzer = analyzer
        self.tools = {}
        self._register_tools()
    
    def _register_tools(self):
        """Initialize tools and inject analyzer if available."""
        for name, tool_class in TOOL_REGISTRY.items():
            tool_instance = tool_class()
            # Inject Analyzer context if the tool supports it
            if hasattr(tool_instance, "set_analyzer") and self.analyzer:
                tool_instance.set_analyzer(self.analyzer)
            self.tools[name] = tool_instance
    
    def execute_instruction(self, instruction: 'BuildingInstruction') -> BuildResult:
        tool_name = instruction.tool_name
        params = instruction.parameters
        
        if tool_name not in self.tools:
            return BuildResult(False, [], tool_name, f"Unknown tool: {tool_name}")
        
        tool = self.tools[tool_name]
        
        # Late binding of analyzer if needed (in case it wasn't ready at init)
        if hasattr(tool, "set_analyzer") and self.analyzer and getattr(tool, "analyzer", None) is None:
             tool.set_analyzer(self.analyzer)

        try:
            blocks = tool.execute(params, self.origin)
            return BuildResult(True, blocks, tool_name, f"Generated {len(blocks)} blocks")
        except Exception as e:
            return BuildResult(False, [], tool_name, f"Execution error: {str(e)}")
    
    def build(self, instructions: List['BuildingInstruction']) -> List[Dict]:
        all_blocks = []
        # Simple dict to prevent duplicate blocks at same coord (last writer wins)
        block_map = {} 
        
        for instruction in instructions:
            result = self.execute_instruction(instruction)
            if result.success:
                for block in result.blocks:
                    block_map[(block.x, block.y, block.z)] = block
        
        # Convert back to list
        for b in block_map.values():
            all_blocks.append(b.to_dict())
            
        return all_blocks

class CarpenterSession:
    def __init__(self, origin: tuple = (0, 64, 0)):
        self.origin = origin
        self.carpenter = Carpenter(origin)
        self.instructions_history = []
        
    def build_from_instructions(self, instructions: List['BuildingInstruction'], analyzer=None) -> List[Dict]:
        # If analyzer provided, re-init carpenter or inject
        if analyzer:
            self.carpenter = Carpenter(self.origin, analyzer)
            
        return self.carpenter.build(instructions)

    def build_from_json(self, json_instructions: List[Dict], analyzer=None) -> List[Dict]:
        instructions = [
            BuildingInstruction(
                tool_name=item.get("tool_name", item.get("tool", "")),
                parameters=item.get("parameters", item.get("params", {}))
            )
            for item in json_instructions
        ]
        return self.build_from_instructions(instructions, analyzer)
        
    def run_bot(self, project_name: str, target_file: str, origin: Optional[tuple] = None):
        """
        Executes the Node.js bot script to build the structure.
        """
        import subprocess
        import os
        
        # Assuming bot is in AI_Carpenter_Bot sibling directory
        # Current file is in app/v2/, so up THREE levels to bananacraft-core
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bot_dir = os.path.join(base_dir, "AI_Carpenter_Bot")
        index_js = os.path.join(bot_dir, "index.js")
        
        if not os.path.exists(index_js):
            print(f"Debug: Bot script not found. Searched in: {bot_dir}")
            raise FileNotFoundError(f"Bot script not found at {index_js}")
            
        cmd = ["node", "index.js", project_name]
        
        # Use provided origin, or session origin, or default
        use_origin = origin if origin is not None else self.origin
        if use_origin:
             cmd.extend([str(use_origin[0]), str(use_origin[1]), str(use_origin[2])])
        else:
             cmd.extend(["0", "64", "0"]) 
        
        if target_file:
            cmd.append(target_file)

        bot_env = os.environ.copy()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=bot_dir,
            env=bot_env,
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Bot Error: {stderr}\nOutput: {stdout}")
        
        return stdout