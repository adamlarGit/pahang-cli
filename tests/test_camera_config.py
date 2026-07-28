"""Tests for CameraConfig."""

import unittest

from src.project.models import CameraConfig


class TestCameraConfig(unittest.TestCase):
    def test_default_config(self) -> None:
        cfg = CameraConfig()
        self.assertEqual(cfg.ir_mode, "single")
        self.assertEqual(cfg.ir_prefix, "FLIR")
        self.assertEqual(cfg.dc_prefix, "DC_")
        self.assertEqual(cfg.dc_offset, 1)
        self.assertEqual(cfg.dg_prefix, "IMG_")

    def test_from_dict_and_to_dict(self) -> None:
        data = {
            "ir_mode": "dual_pair",
            "ir_prefix": "IR_",
            "dc_prefix": "DC_",
            "dc_offset": 2,
            "dg_prefix": "P",
        }
        cfg = CameraConfig.from_dict(data)
        self.assertEqual(cfg.ir_mode, "dual_pair")
        self.assertEqual(cfg.ir_prefix, "IR_")
        self.assertEqual(cfg.dc_offset, 2)
        
        out_dict = cfg.to_dict()
        self.assertEqual(out_dict, data)

if __name__ == "__main__":
    unittest.main()
