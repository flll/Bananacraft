"""
Mesh Loader - Thin wrapper around trimesh for loading 3D models with texture support
"""
import trimesh
import numpy as np
from PIL import Image
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MeshData:
    """Container for mesh geometry data with texture support"""
    vertices: np.ndarray  # (N, 3) float array
    faces: np.ndarray     # (M, 3) int array
    vertex_colors: Optional[np.ndarray] = None  # (N, 4) float array for RGBA
    uv_coords: Optional[np.ndarray] = None      # (N, 2) float array for UV
    texture_image: Optional[Image.Image] = None  # PIL Image for texture
    face_colors: Optional[np.ndarray] = None    # (M, 4) float array for face colors
    
    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (min, max) bounds of the mesh"""
        return self.vertices.min(axis=0), self.vertices.max(axis=0)
    
    @property
    def dimensions(self) -> np.ndarray:
        """Return the dimensions of the mesh bounding box"""
        min_b, max_b = self.bounds
        return max_b - min_b
    
    def has_texture(self) -> bool:
        """Check if texture data is available"""
        return self.uv_coords is not None and self.texture_image is not None
    
    def sample_texture(self, uv: np.ndarray) -> np.ndarray:
        """
        Sample texture color at UV coordinates.
        
        Args:
            uv: (u, v) coordinates in [0, 1] range
            
        Returns:
            RGBA color as float array [0, 1]
        """
        if not self.has_texture():
            return np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        
        # Get texture dimensions
        width, height = self.texture_image.size
        
        # Convert UV to pixel coordinates
        # UV origin is typically bottom-left, image origin is top-left
        u, v = uv[0], uv[1]
        
        # Wrap UVs to [0, 1] range
        u = u % 1.0
        v = v % 1.0
        
        # Convert to pixel coordinates
        x = int(u * (width - 1))
        y = int((1 - v) * (height - 1))  # Flip V for image coordinates
        
        # Clamp to valid range
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        
        # Sample pixel
        pixel = self.texture_image.getpixel((x, y))
        
        # Convert to RGBA float
        if len(pixel) == 4:
            return np.array(pixel, dtype=np.float32) / 255.0
        elif len(pixel) == 3:
            return np.array([pixel[0], pixel[1], pixel[2], 255], dtype=np.float32) / 255.0
        else:
            return np.array([pixel[0], pixel[0], pixel[0], 255], dtype=np.float32) / 255.0


def load_mesh(file_path: str | Path) -> MeshData:
    """
    Load a 3D mesh file (GLB, OBJ, STL, etc.) with texture support.
    
    Args:
        file_path: Path to the 3D model file
        
    Returns:
        MeshData containing vertices, faces, colors, UV coords, and texture
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Mesh file not found: {file_path}")

    ext = file_path.suffix.lower()
    if ext == ".fbx":
        raise ValueError(
            "FBX 形式はこの環境では読み込めません。"
            "Settings の Tripo3D 設定で **quad を OFF**、"
            "Texture Model を使う場合は最新版 (v3.0-20250812) を選び、"
            "「Tripo を必ず再実行」でブループリントを作り直してください。"
        )

    # 拡張子を明示して trimesh に渡す（誤判定防止）
    load_kwargs: dict = {}
    if ext in (".glb", ".gltf", ".obj", ".stl", ".ply"):
        load_kwargs["file_type"] = ext.lstrip(".")

    scene_or_mesh = trimesh.load(str(file_path), **load_kwargs)
    
    # Handle scenes (multi-mesh files like GLB)
    if isinstance(scene_or_mesh, trimesh.Scene):
        # For textured meshes, we need to preserve texture data
        # Try to get the first mesh with its visual data intact
        meshes = []
        for geom in scene_or_mesh.geometry.values():
            if isinstance(geom, trimesh.Trimesh):
                meshes.append(geom)
        
        if not meshes:
            raise ValueError(f"No valid meshes found in {file_path}")
        
        # Use the first mesh (preserve texture) or concatenate if multiple
        if len(meshes) == 1:
            mesh = meshes[0]
        else:
            mesh = trimesh.util.concatenate(meshes)
    else:
        mesh = scene_or_mesh
    
    # Extract vertex colors if available
    vertex_colors = None
    uv_coords = None
    texture_image = None
    face_colors = None
    
    if mesh.visual is not None:
        visual = mesh.visual
        
        # Check for TextureVisuals (has UV and texture)
        if isinstance(visual, trimesh.visual.TextureVisuals):
            # Extract UV coordinates
            if hasattr(visual, 'uv') and visual.uv is not None:
                uv_coords = np.array(visual.uv, dtype=np.float32)
            
            # Extract texture image
            if hasattr(visual, 'material') and visual.material is not None:
                mat = visual.material
                # Try different texture properties
                if hasattr(mat, 'baseColorTexture') and mat.baseColorTexture is not None:
                    texture_image = mat.baseColorTexture
                elif hasattr(mat, 'image') and mat.image is not None:
                    texture_image = mat.image
        
        # Check for ColorVisuals (vertex/face colors)
        elif isinstance(visual, trimesh.visual.ColorVisuals):
            if hasattr(visual, 'vertex_colors') and visual.vertex_colors is not None:
                vertex_colors = visual.vertex_colors.astype(np.float32) / 255.0
            if hasattr(visual, 'face_colors') and visual.face_colors is not None:
                face_colors = visual.face_colors.astype(np.float32) / 255.0
        
        # Also try direct attribute access
        if vertex_colors is None and hasattr(visual, 'vertex_colors') and visual.vertex_colors is not None:
            vertex_colors = visual.vertex_colors.astype(np.float32) / 255.0
    
    return MeshData(
        vertices=np.array(mesh.vertices, dtype=np.float32),
        faces=np.array(mesh.faces, dtype=np.int32),
        vertex_colors=vertex_colors,
        uv_coords=uv_coords,
        texture_image=texture_image,
        face_colors=face_colors
    )


def scale_mesh_to_size(mesh: MeshData, target_size: int, constraint_axis: str = 'y') -> tuple[MeshData, float]:
    """
    Scale mesh so that the constraint axis has the target size.
    
    Args:
        mesh: Input mesh data
        target_size: Desired size along the constraint axis
        constraint_axis: Which axis to constrain ('x', 'y', or 'z')
        
    Returns:
        Tuple of (scaled MeshData, scale factor)
    """
    dimensions = mesh.dimensions
    axis_index = {'x': 0, 'y': 1, 'z': 2}[constraint_axis.lower()]
    
    # Calculate scale factor
    scale = (target_size - 1) / dimensions[axis_index]
    
    # Scale vertices
    scaled_vertices = mesh.vertices * scale
    
    return MeshData(
        vertices=scaled_vertices,
        faces=mesh.faces,
        vertex_colors=mesh.vertex_colors,
        uv_coords=mesh.uv_coords,
        texture_image=mesh.texture_image,
        face_colors=mesh.face_colors
    ), scale


def normalize_mesh_position(mesh: MeshData) -> MeshData:
    """
    Move mesh so all coordinates are positive (like legacy voxelizer).
    Translates the mesh so its minimum bound is at origin.
    
    Args:
        mesh: Input mesh data
        
    Returns:
        MeshData with normalized positions
    """
    min_bound = mesh.vertices.min(axis=0)
    normalized_vertices = mesh.vertices - min_bound
    
    return MeshData(
        vertices=normalized_vertices,
        faces=mesh.faces,
        vertex_colors=mesh.vertex_colors,
        uv_coords=mesh.uv_coords,
        texture_image=mesh.texture_image,
        face_colors=mesh.face_colors
    )
