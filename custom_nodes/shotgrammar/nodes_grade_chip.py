"""ComfyUI wrapper for shotgrammar.grade_chip. Imports cleanly without ComfyUI."""
from __future__ import annotations

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import grade_chip as gc
except ImportError:  # loaded as a plain module (tests, scripts)
    import grade_chip as gc


class SGGradeChip:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "chip": (gc.CHIP_NAMES,),
                "grain_amount": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, images, chip, grain_amount, seed):
        rgb = images.cpu().numpy()[..., :3]
        return (torch.from_numpy(gc.apply_chip(rgb, chip, grain_amount, seed)),)


NODE_CLASS_MAPPINGS = {"SGGradeChip": SGGradeChip}
NODE_DISPLAY_NAME_MAPPINGS = {"SGGradeChip": "SG Grade Chip"}
