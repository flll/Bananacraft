"""
Block Assigner - Match voxel colors to Minecraft blocks using atlas data
"""
import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Literal
from .voxel_mesh import VoxelMesh, Voxel, FaceVisibility
from .dithering import apply_dithering, bin_color
from .smooth_block_placer import (
    determine_block_shape,
    get_smooth_block_name,
    can_smooth_block,
    BlockShape,
    SmoothBlockInfo
)


@dataclass
class BlockFace:
    """Color and standard deviation for a block face"""
    color: np.ndarray  # RGBA [0, 1]
    std: float = 0.0


@dataclass
class AtlasBlock:
    """Block data from vanilla.atlas"""
    name: str
    color: np.ndarray  # Global average RGBA [0, 1]
    faces: dict[str, BlockFace]  # up, down, north, south, east, west


@dataclass
class AssignedBlock:
    """A voxel with its assigned Minecraft block"""
    position: tuple[int, int, int]
    voxel_color: np.ndarray  # Original RGBA [0, 1]
    block_name: str
    block_state: str = ""  # Block state suffix e.g. [facing=north,half=bottom]
    shape: str = "full"  # 'full', 'slab_bottom', 'slab_top', 'stair'
    
    def get_full_block_id(self) -> str:
        """Get the full block ID with state for Minecraft commands"""
        return f"{self.block_name}{self.block_state}"


class BlockAtlas:
    """
    Manages the atlas of Minecraft block colors.
    Loads from vanilla.atlas JSON file.
    """
    
    def __init__(self, atlas_path: Optional[str | Path] = None):
        """
        Load the atlas from a JSON file.
        
        Args:
            atlas_path: Path to vanilla.atlas, or None to use default
        """
        if atlas_path is None:
            # Default to the bundled atlas
            atlas_path = Path(__file__).parent / 'vanilla.atlas'
        
        self.blocks: dict[str, AtlasBlock] = {}
        self._load_atlas(atlas_path)
    
    def _load_atlas(self, atlas_path: str | Path) -> None:
        """Load atlas data from JSON file"""
        with open(atlas_path, 'r') as f:
            data = json.load(f)
        
        for block_data in data.get('blocks', []):
            name = block_data['name']
            
            # Parse global color
            color = np.array([
                block_data['colour']['r'],
                block_data['colour']['g'],
                block_data['colour']['b'],
                block_data['colour']['a']
            ], dtype=np.float32)
            
            # Parse face colors if available
            faces = {}
            if 'faceColours' in block_data:
                for face_name, face_data in block_data['faceColours'].items():
                    faces[face_name] = BlockFace(
                        color=np.array([
                            face_data['colour']['r'],
                            face_data['colour']['g'],
                            face_data['colour']['b'],
                            face_data['colour']['a']
                        ], dtype=np.float32),
                        std=face_data.get('std', 0.0)
                    )
            else:
                # Use global color for all faces if face colors not available
                for face_name in ['up', 'down', 'north', 'south', 'east', 'west']:
                    faces[face_name] = BlockFace(color=color.copy())
            
            self.blocks[name] = AtlasBlock(name=name, color=color, faces=faces)
    
    def get_block(self, name: str) -> Optional[AtlasBlock]:
        """Get a block by name"""
        return self.blocks.get(name)
    
    def get_all_block_names(self) -> list[str]:
        """Get all block names in the atlas"""
        return list(self.blocks.keys())


class BlockAssigner:
    """
    Assigns Minecraft blocks to voxels based on color matching.
    """
    
    # Default block palette - common blocks that work well for most builds
    DEFAULT_PALETTE = [
        'minecraft:white_wool', 'minecraft:orange_wool', 'minecraft:magenta_wool',
        'minecraft:light_blue_wool', 'minecraft:yellow_wool', 'minecraft:lime_wool',
        'minecraft:pink_wool', 'minecraft:gray_wool', 'minecraft:light_gray_wool',
        'minecraft:cyan_wool', 'minecraft:purple_wool', 'minecraft:blue_wool',
        'minecraft:brown_wool', 'minecraft:green_wool', 'minecraft:red_wool',
        'minecraft:black_wool',
        'minecraft:white_concrete', 'minecraft:orange_concrete', 'minecraft:magenta_concrete',
        'minecraft:light_blue_concrete', 'minecraft:yellow_concrete', 'minecraft:lime_concrete',
        'minecraft:pink_concrete', 'minecraft:gray_concrete', 'minecraft:light_gray_concrete',
        'minecraft:cyan_concrete', 'minecraft:purple_concrete', 'minecraft:blue_concrete',
        'minecraft:brown_concrete', 'minecraft:green_concrete', 'minecraft:red_concrete',
        'minecraft:black_concrete',
        'minecraft:white_terracotta', 'minecraft:orange_terracotta', 'minecraft:magenta_terracotta',
        'minecraft:light_blue_terracotta', 'minecraft:yellow_terracotta', 'minecraft:lime_terracotta',
        'minecraft:pink_terracotta', 'minecraft:gray_terracotta', 'minecraft:light_gray_terracotta',
        'minecraft:cyan_terracotta', 'minecraft:purple_terracotta', 'minecraft:blue_terracotta',
        'minecraft:brown_terracotta', 'minecraft:green_terracotta', 'minecraft:red_terracotta',
        'minecraft:black_terracotta', 'minecraft:terracotta',
        'minecraft:stone', 'minecraft:granite', 'minecraft:diorite', 'minecraft:andesite',
        'minecraft:deepslate', 'minecraft:cobblestone', 'minecraft:oak_planks',
        'minecraft:spruce_planks', 'minecraft:birch_planks', 'minecraft:jungle_planks',
        'minecraft:acacia_planks', 'minecraft:dark_oak_planks', 'minecraft:sand',
        'minecraft:sandstone', 'minecraft:red_sand', 'minecraft:red_sandstone',
        'minecraft:bricks', 'minecraft:prismarine', 'minecraft:netherrack',
        'minecraft:obsidian', 'minecraft:gold_block', 'minecraft:iron_block',
        'minecraft:diamond_block', 'minecraft:emerald_block', 'minecraft:lapis_block',
        'minecraft:quartz_block', 'minecraft:bone_block', 'minecraft:snow_block',
        'minecraft:honeycomb_block', 'minecraft:honey_block',
    ]
    
    def __init__(
        self,
        atlas: Optional[BlockAtlas] = None,
        palette: Optional[list[str]] = None
    ):
        """
        Initialize the block assigner.
        
        Args:
            atlas: Block atlas to use, or None to load default
            palette: List of block names to use, or None for default palette
        """
        self.atlas = atlas or BlockAtlas()
        self.palette = palette or self.DEFAULT_PALETTE
        
        # Filter palette to only include blocks that exist in atlas
        self.palette = [b for b in self.palette if b in self.atlas.blocks]
        
        # Cache for color -> block lookups
        self._cache: dict[int, str] = {}
    
    def _color_distance_squared(self, c1: np.ndarray, c2: np.ndarray) -> float:
        """Calculate squared RGB distance between two colors"""
        return float(np.sum((c1[:3] - c2[:3]) ** 2))
    
    def _get_contextual_color(
        self,
        block: AtlasBlock,
        face_visibility: FaceVisibility
    ) -> tuple[np.ndarray, float]:
        """
        Get the average color of visible faces.
        
        Returns:
            Tuple of (average color, average std)
        """
        if face_visibility == FaceVisibility.NONE:
            return block.color, 0.0
        
        colors = []
        stds = []
        
        if FaceVisibility.UP in face_visibility:
            colors.append(block.faces['up'].color)
            stds.append(block.faces['up'].std)
        if FaceVisibility.DOWN in face_visibility:
            colors.append(block.faces['down'].color)
            stds.append(block.faces['down'].std)
        if FaceVisibility.NORTH in face_visibility:
            colors.append(block.faces['north'].color)
            stds.append(block.faces['north'].std)
        if FaceVisibility.SOUTH in face_visibility:
            colors.append(block.faces['south'].color)
            stds.append(block.faces['south'].std)
        if FaceVisibility.EAST in face_visibility:
            colors.append(block.faces['east'].color)
            stds.append(block.faces['east'].std)
        if FaceVisibility.WEST in face_visibility:
            colors.append(block.faces['west'].color)
            stds.append(block.faces['west'].std)
        
        if not colors:
            return block.color, 0.0
        
        avg_color = np.mean(colors, axis=0)
        avg_std = np.mean(stds)
        
        return avg_color, avg_std
    
    def find_best_block(
        self,
        color: np.ndarray,
        face_visibility: FaceVisibility = FaceVisibility.ALL,
        use_contextual: bool = True,
        error_weight: float = 0.0
    ) -> str:
        """
        Find the best matching block for a color.
        
        Args:
            color: RGBA color [0, 1]
            face_visibility: Which faces are visible
            use_contextual: Whether to use face-specific colors
            error_weight: Weight for texture variance in error calculation
            
        Returns:
            Block name that best matches the color
        """
        # Create cache key from color (quantize to reduce cache size)
        color_255 = (color[:3] * 255).astype(int)
        cache_key = (color_255[0] << 16) | (color_255[1] << 8) | color_255[2]
        cache_key = (cache_key << 6) | int(face_visibility)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Find best matching block
        best_block = None
        best_error = float('inf')
        
        for block_name in self.palette:
            block = self.atlas.blocks[block_name]
            
            if use_contextual and face_visibility != FaceVisibility.NONE:
                block_color, block_std = self._get_contextual_color(block, face_visibility)
            else:
                block_color = block.color
                block_std = 0.0
            
            # Calculate error (RGB distance + optional std weighting)
            rgb_error = self._color_distance_squared(color, block_color)
            total_error = rgb_error * (1 - error_weight) + block_std * error_weight
            
            if total_error < best_error:
                best_error = total_error
                best_block = block_name
        
        self._cache[cache_key] = best_block
        return best_block
    
    def assign_blocks(
        self,
        voxel_mesh: VoxelMesh,
        dithering: Literal['off', 'ordered', 'random'] = 'ordered',
        dithering_magnitude: float = 32.0,
        resolution: int = 32,
        use_contextual: bool = True,
        error_weight: float = 0.0,
        enable_smooth_blocks: bool = False,
        progress_callback: Optional[callable] = None
    ) -> list[AssignedBlock]:
        """
        Assign Minecraft blocks to all voxels in a mesh.
        
        Args:
            voxel_mesh: VoxelMesh containing voxels
            dithering: Dithering type ('off', 'ordered', 'random')
            dithering_magnitude: Dithering strength
            resolution: Color quantization resolution
            use_contextual: Use face-specific colors
            error_weight: Weight for texture variance
            enable_smooth_blocks: If True, use stairs/slabs for diagonal surfaces
            progress_callback: Optional progress callback
            
        Returns:
            List of AssignedBlock objects
        """
        voxels = voxel_mesh.get_all_voxels()
        results = []
        
        for i, voxel in enumerate(voxels):
            # Get face visibility for contextual averaging
            # Apply dithering if requested
            color = voxel.color.copy()
            if dithering != 'off':
                color = apply_dithering(
                    color, 
                    voxel.position, 
                    dithering, 
                    dithering_magnitude
                )
            
            # Find best matching block
            if use_contextual:
                # Calculate face visibility for contextual matching
                visibility = voxel_mesh.get_face_visibility(voxel.position)
            else:
                visibility = FaceVisibility.NONE
            
            block_name = self.find_best_block(
                color, 
                visibility, 
                use_contextual,
                error_weight
            )
            
            block_state = ""
            shape = "full"
            
            # Smooth block logic
            if enable_smooth_blocks and voxel.normal is not None:
                smooth_info = determine_block_shape(voxel.normal)
                
                if smooth_info.shape != BlockShape.FULL and can_smooth_block(block_name):
                    new_name, block_state = get_smooth_block_name(block_name, smooth_info)
                    block_name = new_name
                    shape = smooth_info.shape.name.lower()
            
            results.append(AssignedBlock(
                position=voxel.position,
                voxel_color=voxel.color,
                block_name=block_name,
                block_state=block_state,
                shape=shape
            ))
            
            if progress_callback and i % 1000 == 0:
                progress_callback(i / len(voxels))
                
        if progress_callback:
            progress_callback(1.0)
            
        return results

    def _assign_blocks_batch(
        self,
        voxels: list[Voxel],
        dithering: str,
        dithering_magnitude: float
    ) -> list[AssignedBlock]:
        """
        Fast block assignment using numpy broadcasting.
        Ignores face visibility context for performance.
        """
        if not voxels:
            return []
            
        import time
        t0 = time.time()
        print(f"[BlockAssigner] Batch processing started for {len(voxels)} voxels...")
            
        # Prepare palette
        palette_names = self.palette
        # (M, 3)
        palette_colors = np.array([self.atlas.blocks[name].color[:3] for name in palette_names])
        print(f"[BlockAssigner] Palette prepared: {len(palette_names)} blocks")
        
        # Prepare voxels
        # (N, 3)
        print(f"[BlockAssigner] Converting {len(voxels)} voxels to numpy array...")
        voxel_colors = np.array([v.color[:3] for v in voxels])
        positions = np.array([v.position for v in voxels])
        print(f"[BlockAssigner] Voxel arrays prepared in {time.time() - t0:.2f}s")
        
        # Apply dithering (vectorized-ish manual loop for now to be safe, or skip)
        # Implementing simple ordered dithering vectorized is possible but complex.
        # Let's do a simple noise addition if random, for ordered it's position based.
        
        # For speed, let's process in chunks
        chunk_size = 10000
        results = []
        
        for i in range(0, len(voxels), chunk_size):
            # Extract chunk
            v_colors = voxel_colors[i:i+chunk_size].copy() # (B, 3)
            v_pos = positions[i:i+chunk_size] # (B, 3)
            
            # Apply dithering (Simplified for performance)
            if dithering == 'random':
                noise = (np.random.random(v_colors.shape) - 0.5) * (dithering_magnitude / 255.0)
                v_colors = np.clip(v_colors + noise, 0, 1)
            elif dithering == 'ordered':
                # Simplified ordered dithering based on position sum
                # Bayer-like pattern based on (x+y+z)%something
                factors = ((v_pos[:, 0] + v_pos[:, 1] + v_pos[:, 2]) % 4) / 4.0 - 0.5
                noise = factors[:, np.newaxis] * (dithering_magnitude / 255.0)
                v_colors = np.clip(v_colors + noise, 0, 1)
            
            # Find closest colors
            # (B, 1, 3) - (1, M, 3) -> (B, M, 3) 
            diff = v_colors[:, np.newaxis, :] - palette_colors[np.newaxis, :, :]
            dists = np.sum(diff**2, axis=2) # (B, M)
            best_indices = np.argmin(dists, axis=1) # (B,)
            
            # Create AssignedBlock objects
            for j, idx in enumerate(best_indices):
                # Map back to global index
                orig_idx = i + j
                results.append(AssignedBlock(
                    position=tuple(v_pos[j]),
                    voxel_color=voxel_colors[orig_idx], # Original color
                    block_name=palette_names[idx]
                ))
        
        print(f"[BlockAssigner] Batch assignment finished in {time.time() - t0:.2f}s")
        return results
