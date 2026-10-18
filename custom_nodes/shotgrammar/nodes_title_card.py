"""ComfyUI wrapper for shotgrammar.title_card. Imports cleanly without ComfyUI."""
from __future__ import annotations

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import title_card as tc
except ImportError:  # loaded as a plain module (tests, scripts)
    import title_card as tc


class SGTitleCard:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "title": ("STRING", {"default": "TITLE"}),
                "subtitle": ("STRING", {"default": ""}),
                "style": (tc.STYLES,),
                "hold_frames": ("INT", {"default": 24, "min": 1, "max": 257}),
                "fade_in_frames": ("INT", {"default": 8, "min": 0, "max": 257}),
                "position": (tc.POSITIONS, {"default": "lower_third"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("frames", "poster")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, image, title, subtitle, style, hold_frames, fade_in_frames, position):
        frames, poster = tc.title_card(
            image[0].cpu().numpy(), title, subtitle, style, position, hold_frames, fade_in_frames
        )
        return (torch.from_numpy(frames), torch.from_numpy(poster)[None])


NODE_CLASS_MAPPINGS = {"SGTitleCard": SGTitleCard}
NODE_DISPLAY_NAME_MAPPINGS = {"SGTitleCard": "SG Title Card"}
