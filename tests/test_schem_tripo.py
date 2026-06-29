"""schem プレビュー / Tripo block_size のスモークテスト（stdlib unittest）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from v2.block_texture_resolver import resolve_block_faces
from v2.tripo_config import stylize_block_for_target


class TestStylizeBlockSize(unittest.TestCase):
    def test_small_zone(self):
        self.assertEqual(stylize_block_for_target(12), 128)
        self.assertEqual(stylize_block_for_target(4), 128)

    def test_large_zone(self):
        self.assertEqual(stylize_block_for_target(96), 32)


class TestBlockTextureResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from v2 import mc_assets

        assets = mc_assets.ensure_official_assets()
        if not assets or not assets.get("textures"):
            raise unittest.SkipTest("official jar textures unavailable")
        cls.jar = assets["textures"]

    def test_birch_leaves(self):
        r = resolve_block_faces("minecraft:birch_leaves", jar_textures=self.jar)
        self.assertTrue(r.up.is_file())

    def test_unknown_block_stone_fallback(self):
        r = resolve_block_faces("minecraft:totally_unknown_block", jar_textures=self.jar)
        for face in (r.up, r.down, r.north, r.south, r.east, r.west):
            self.assertTrue(face.is_file())


class TestSchemWriterRoundtrip(unittest.TestCase):
    def test_write_and_read_roundtrip(self):
        import tempfile

        from v2.schem_preview import parse_schem_blocks, schem_dimensions
        from v2.schem_writer import write_schem_from_blocks

        blocks = [
            {"x": 0, "y": 0, "z": 0, "type": "minecraft:stone"},
            {"x": 1, "y": 0, "z": 0, "type": "minecraft:oak_planks"},
            {"x": 0, "y": 1, "z": 0, "type": "minecraft:glass"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".schem", delete=False) as tmp:
            path = tmp.name
        try:
            write_schem_from_blocks(blocks, path)
            w, h, l = schem_dimensions(path)
            self.assertEqual((w, h, l), (2, 2, 1))
            loaded = parse_schem_blocks(path)
            self.assertEqual(len(loaded), 3)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_y_layer_filter(self):
        import tempfile

        from v2.schem_preview import parse_schem_blocks
        from v2.schem_writer import write_schem_from_blocks

        blocks = [
            {"x": 0, "y": 0, "z": 0, "type": "minecraft:stone"},
            {"x": 0, "y": 1, "z": 0, "type": "minecraft:dirt"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".schem", delete=False) as tmp:
            path = tmp.name
        try:
            write_schem_from_blocks(blocks, path)
            layer0 = parse_schem_blocks(path, y_layer=0)
            self.assertEqual(len(layer0), 1)
            self.assertEqual(layer0[0]["type"], "minecraft:stone")
        finally:
            Path(path).unlink(missing_ok=True)


class TestSchemResize(unittest.TestCase):
    def test_scale_blocks_to_footprint(self):
        from v2.schem_resize import scale_blocks_to_footprint

        blocks = [
            {"x": 0, "y": 0, "z": 0, "type": "minecraft:stone"},
            {"x": 9, "y": 0, "z": 9, "type": "minecraft:dirt"},
        ]
        scaled, was = scale_blocks_to_footprint(blocks, target_footprint=5)
        self.assertTrue(was)
        max_x = max(int(b["x"]) for b in scaled)
        max_z = max(int(b["z"]) for b in scaled)
        self.assertLessEqual(max(max_x, max_z), 5)

    def test_auto_resize_schem_file(self):
        import tempfile

        from v2.schem_preview import schem_dimensions
        from v2.schem_resize import auto_resize_schem_file
        from v2.schem_writer import write_schem_from_blocks

        blocks = [
            {"x": x, "y": 0, "z": z, "type": "minecraft:stone"}
            for x in range(20)
            for z in range(20)
        ]
        with tempfile.NamedTemporaryFile(suffix=".schem", delete=False) as tmp:
            path = tmp.name
        try:
            write_schem_from_blocks(blocks, path)
            self.assertTrue(auto_resize_schem_file(path, 12, 12))
            w, _h, l = schem_dimensions(path)
            self.assertLessEqual(max(w, l), 12)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_replace_block_type(self):
        import tempfile

        from v2.schem_preview import parse_schem_blocks
        from v2.schem_resize import replace_block_type_in_schem
        from v2.schem_writer import write_schem_from_blocks

        blocks = [
            {"x": 0, "y": 0, "z": 0, "type": "minecraft:oak_planks"},
            {"x": 1, "y": 0, "z": 0, "type": "minecraft:stone"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".schem", delete=False) as tmp:
            path = tmp.name
        try:
            write_schem_from_blocks(blocks, path)
            n = replace_block_type_in_schem(path, "minecraft:oak_planks", "minecraft:spruce_planks")
            self.assertEqual(n, 1)
            loaded = parse_schem_blocks(path)
            types = {b["type"] for b in loaded}
            self.assertIn("minecraft:spruce_planks", types)
            self.assertNotIn("minecraft:oak_planks", types)
        finally:
            Path(path).unlink(missing_ok=True)


class TestSchemGlbBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schem = Path("/minecraft-data/plugins/WorldEdit/schematics/building_15.schem")
        if not schem.is_file():
            schem = ROOT / "minecraft-data/plugins/WorldEdit/schematics/building_15.schem"
        if not schem.is_file():
            raise unittest.SkipTest("building_15.schem not present")
        cls.schem = schem
        from v2 import mc_assets

        assets = mc_assets.ensure_official_assets()
        if not assets or not assets.get("textures"):
            raise unittest.SkipTest("official jar textures unavailable")
        cls.jar = assets["textures"]

    def test_build_glb(self):
        from v2.schem_glb_builder import build_schem_glb
        from v2.schem_preview import parse_schem_blocks

        blocks = parse_schem_blocks(str(self.schem))
        glb = build_schem_glb(blocks, self.jar)
        self.assertEqual(glb[:4], b"glTF")
        self.assertGreater(len(blocks), 0)


if __name__ == "__main__":
    unittest.main()
