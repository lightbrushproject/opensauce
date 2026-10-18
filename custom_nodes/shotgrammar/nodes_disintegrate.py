"""ComfyUI wrapper for shotgrammar.disintegrate. Imports cleanly without ComfyUI."""
from __future__ import annotations

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import disintegrate as di
except ImportError:  # loaded as a plain module (tests, scripts)
    import disintegrate as di


class SGDisintegrate:
    """Guide frames for a subject crumbling into ash and embers: photo where intact, clean plate where gone."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "plate": ("IMAGE",),
                "mask": ("MASK",),
                "n_frames": ("INT", {"default": 97, "min": 9, "max": 1025, "step": 8}),
                "start": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.9, "step": 0.01}),
                "end": ("FLOAT", {"default": 0.85, "min": 0.1, "max": 1.0, "step": 0.01}),
                "wind_x": ("FLOAT", {"default": -1.0, "min": -2.0, "max": 2.0, "step": 0.05}),
                "wind_y": ("FLOAT", {"default": -0.3, "min": -2.0, "max": 2.0, "step": 0.05}),
                "density": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
            },
            "optional": {
                "body_base": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "pin": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "wake": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("frames", "weights")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, image, plate, mask, n_frames, start, end, wind_x, wind_y, density, seed, body_base=0.5, pin=0.85,
            wake=0.4):
        frames, wts = di.guide_sequence(image[0].cpu().numpy(), plate[0].cpu().numpy(), mask[0].cpu().numpy(),
                                        n_frames, start, end, wind_x, wind_y, density, seed, body_base, pin, wake)
        # weights as a grey IMAGE batch: ImageFromBatch + ImageToMask feed LTXVAddGuide.attention_mask per key
        return (torch.from_numpy(frames), torch.from_numpy(wts[..., None].repeat(3, axis=-1)))


class SGRemovalMask:
    """Area the clean plate repaints: subject grown for glow halos plus a floor patch for shadows and cast light."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
                "grow_frac": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.3, "step": 0.005}),
                "below_frac": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.5, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, mask, grow_frac, below_frac):
        return (torch.from_numpy(di.removal_mask(mask[0].cpu().numpy(), grow_frac, below_frac))[None],)


NODE_CLASS_MAPPINGS = {"SGDisintegrate": SGDisintegrate, "SGRemovalMask": SGRemovalMask}
NODE_DISPLAY_NAME_MAPPINGS = {"SGDisintegrate": "SG Disintegrate (guide frames)", "SGRemovalMask": "SG Removal Mask"}
