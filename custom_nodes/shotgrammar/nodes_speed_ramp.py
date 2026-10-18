"""ComfyUI wrapper for shotgrammar.speed_ramp. Imports cleanly without ComfyUI."""
from __future__ import annotations

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import speed_ramp as sr
except ImportError:  # loaded as a plain module (tests, scripts)
    import speed_ramp as sr


class SGSpeedRamp:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "curve": (sr.CURVES,),
                "hit_at": ("FLOAT", {"default": 0.6, "min": 0.05, "max": 0.9, "step": 0.01}),
                "blend": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "out_frames": ("INT", {"default": 0, "min": 0, "max": 1025}),
                # STRING link that wins over `curve` (e.g. SGCameraMove.ramp_curve); combos refuse STRING links
                "curve_override": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, images, curve, hit_at, blend, out_frames=0, curve_override=None):
        curve = curve_override or curve
        if curve not in sr.CURVES:
            raise ValueError(f"unknown curve {curve!r}; known: {', '.join(sr.CURVES)}")
        # out_frames 0 = keep the input frame count
        arr = images.cpu().numpy()
        out = sr.speed_ramp(arr, curve, out_frames or None, hit_at, blend)
        return (torch.from_numpy(out),)


NODE_CLASS_MAPPINGS = {"SGSpeedRamp": SGSpeedRamp}
NODE_DISPLAY_NAME_MAPPINGS = {"SGSpeedRamp": "SG Speed Ramp"}
