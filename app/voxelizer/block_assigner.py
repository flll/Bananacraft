"""
Block Assigner - Match voxel colors to Minecraft blocks using atlas data.

色距離はデフォルトで CIE-LAB の ΔE (CIE76 ベース) を使う。RGB ユークリッドより
人間の視覚に近く、「茶色羊毛 vs oak_log」「黄色羊毛 vs honey_block」のような
近い色帯での誤マッチを減らせる。

また、`palette` が `BlockAssigner.DEFAULT_PALETTE` ではなくテーマ別に絞られたリスト
として渡された場合は、リスト先頭ほど「主役素材」として優先するよう距離に小さな
ボーナスを乗せる（自然素材ボーナス）。同色帯で `honey_block` と `yellow_concrete`
が拮抗したとき、パレット先頭の `honey_block` を選びやすくする。
"""
import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal, Optional
from .voxel_mesh import VoxelMesh, Voxel, FaceVisibility
from .dithering import apply_dithering, bin_color
from .smooth_block_placer import (
    determine_block_shape,
    get_smooth_block_name,
    can_smooth_block,
    BlockShape,
    SmoothBlockInfo
)

try:
    import colour as _colour  # type: ignore
    _HAS_COLOUR = True
except ImportError:
    _colour = None
    _HAS_COLOUR = False


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB [0,1] -> CIE Lab. (N, 3) または (3,) どちらでも受け取る。"""
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, 3)
        squeeze = True
    else:
        squeeze = False
    arr = np.clip(arr[:, :3], 0.0, 1.0)
    if _HAS_COLOUR:
        lab = _colour.XYZ_to_Lab(_colour.sRGB_to_XYZ(arr))
    else:
        # フォールバック: D65 simplified sRGB -> XYZ -> Lab
        def _srgb_inv_gamma(c: np.ndarray) -> np.ndarray:
            return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        lin = _srgb_inv_gamma(arr)
        m = np.array([
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ])
        xyz = lin @ m.T
        ref_white = np.array([0.95047, 1.0, 1.08883])
        norm = xyz / ref_white
        eps = (6 / 29) ** 3
        kappa = 1 / 3 * (29 / 6) ** 2

        def f(t: np.ndarray) -> np.ndarray:
            return np.where(t > eps, np.cbrt(t), kappa * t + 4 / 29)
        fx, fy, fz = f(norm[:, 0]), f(norm[:, 1]), f(norm[:, 2])
        L = 116.0 * fy - 16.0
        a = 500.0 * (fx - fy)
        b = 200.0 * (fy - fz)
        lab = np.stack([L, a, b], axis=1)
    return lab[0] if squeeze else lab


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
        palette: Optional[list[str]] = None,
        *,
        palette_bias_strength: float = 0.0,
    ):
        """
        Initialize the block assigner.
        
        Args:
            atlas: Block atlas to use, or None to load default
            palette: List of block names to use, or None for default palette.
                When a curated theme palette is provided, the order matters:
                blocks earlier in the list get a small distance bonus
                (controlled by `palette_bias_strength`) so that they are
                preferred over later candidates when colors are close.
            palette_bias_strength: ΔE units of bonus given to the first palette
                entry; the last entry gets zero. Set to 0.0 to disable bias.
                If None and palette is curated (different from DEFAULT_PALETTE)
                we auto-set this to 4.0 (~ just-noticeable LAB difference).
        """
        self.atlas = atlas or BlockAtlas()
        provided_palette = palette is not None
        self.palette = palette or self.DEFAULT_PALETTE
        
        # Filter palette to only include blocks that exist in atlas
        self.palette = [b for b in self.palette if b in self.atlas.blocks]
        
        # Auto-enable palette bias when a curated theme palette is provided.
        if palette_bias_strength <= 0 and provided_palette:
            palette_bias_strength = 4.0
        self.palette_bias_strength = float(palette_bias_strength)

        # Precompute LAB colors for the active palette (global avg).
        self._palette_lab_global = self._compute_palette_lab(use_faces=False)
        # Face-specific LAB cache: face_visibility bitmask -> (M, 3) Lab.
        self._palette_lab_face_cache: dict[int, np.ndarray] = {}

        # Per-entry palette bias in ΔE units (positive = subtract from error).
        n = len(self.palette)
        if n > 1 and self.palette_bias_strength > 0:
            # Linear from `palette_bias_strength` down to 0 over the palette.
            self._palette_bias = np.linspace(
                self.palette_bias_strength, 0.0, n, dtype=np.float64
            )
        else:
            self._palette_bias = np.zeros(n, dtype=np.float64)

        # Cache for color -> block lookups
        self._cache: dict[int, str] = {}

    def _compute_palette_lab(self, use_faces: bool, face_visibility: int = 0) -> np.ndarray:
        """Compute (M, 3) LAB array for the current palette.

        When `use_faces` is True, average across the visible faces specified by
        `face_visibility` (bitmask compatible with `FaceVisibility`).
        """
        if not use_faces:
            rgbs = np.stack([self.atlas.blocks[name].color[:3] for name in self.palette])
            return _rgb_to_lab(rgbs)

        face_axes = [
            (FaceVisibility.UP, "up"),
            (FaceVisibility.DOWN, "down"),
            (FaceVisibility.NORTH, "north"),
            (FaceVisibility.SOUTH, "south"),
            (FaceVisibility.EAST, "east"),
            (FaceVisibility.WEST, "west"),
        ]
        rgbs = np.empty((len(self.palette), 3), dtype=np.float64)
        for i, name in enumerate(self.palette):
            block = self.atlas.blocks[name]
            colors = []
            for flag, fname in face_axes:
                if face_visibility & int(flag):
                    face = block.faces.get(fname)
                    if face is not None:
                        colors.append(face.color[:3])
            if not colors:
                rgbs[i] = block.color[:3]
            else:
                rgbs[i] = np.mean(np.stack(colors), axis=0)
        return _rgb_to_lab(rgbs)

    def _color_distance_squared(self, c1: np.ndarray, c2: np.ndarray) -> float:
        """Calculate squared RGB distance between two colors (legacy)."""
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
        Find the best matching block for a color, using CIE-LAB ΔE.

        Args:
            color: RGBA color [0, 1]
            face_visibility: Which faces are visible
            use_contextual: Whether to use face-specific colors
            error_weight: (unused, kept for API compatibility)

        Returns:
            Block name that best matches the color
        """
        # Create cache key from color (quantize to reduce cache size)
        color_255 = (np.clip(color[:3], 0.0, 1.0) * 255).astype(int)
        cache_key = (color_255[0] << 16) | (color_255[1] << 8) | color_255[2]
        cache_key = (cache_key << 6) | int(face_visibility)

        if cache_key in self._cache:
            return self._cache[cache_key]

        target_lab = _rgb_to_lab(color[:3])

        if use_contextual and face_visibility != FaceVisibility.NONE:
            fv_key = int(face_visibility)
            palette_lab = self._palette_lab_face_cache.get(fv_key)
            if palette_lab is None:
                palette_lab = self._compute_palette_lab(
                    use_faces=True, face_visibility=fv_key
                )
                self._palette_lab_face_cache[fv_key] = palette_lab
        else:
            palette_lab = self._palette_lab_global

        # ΔE (CIE76) = Euclidean in Lab
        deltas = np.linalg.norm(palette_lab - target_lab[np.newaxis, :], axis=1)
        # Apply palette ordering bias: subtract bias from delta to make earlier
        # entries effectively "closer".
        biased = deltas - self._palette_bias
        best_idx = int(np.argmin(biased))
        best_block = self.palette[best_idx]

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
