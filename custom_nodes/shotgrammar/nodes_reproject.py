"""ComfyUI wrapper for shotgrammar.reproject. Imports cleanly without ComfyUI."""
from __future__ import annotations

import numpy as np

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import reproject as rp
except ImportError:  # loaded as a plain module (tests, scripts)
    import reproject as rp

MOVES = ["dolly_zoom_in", "dolly_zoom_out", "crash_zoom", "push_in", "pull_out"]


class SGReprojectMove:
    @classmethod
    def INPUT_TYPES(cls):
        def f(default):
            return ("FLOAT", {"default": default, "min": 0.0, "max": 1.0, "step": 0.01})

        return {
            "required": {
                "image": ("IMAGE",),
                "depth": ("IMAGE",),
                "move": (MOVES,),
                "n_frames": ("INT", {"default": 49, "min": 1, "max": 257}),
                "intensity": f(0.5),
                "bbox_x0": f(0.3),
                "bbox_y0": f(0.3),
                "bbox_x1": f(0.7),
                "bbox_y1": f(0.7),
                "ease": (list(rp.EASES),),
                "fill_holes": ("BOOLEAN", {"default": True}),
            },
            # STRING links that win over the combos (e.g. SGCameraMove.reproject_move / reproject_ease):
            # ComfyUI and the frontend both refuse a STRING link into a combo input.
            "optional": {
                "move_override": ("STRING", {"forceInput": True}),
                "ease_override": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("frames", "hole_mask")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(
        self, image, depth, move, n_frames, intensity, bbox_x0, bbox_y0, bbox_x1, bbox_y1, ease, fill_holes=True,
        move_override=None, ease_override=None,
    ):
        move = move_override or move
        ease = ease_override or ease
        if move not in MOVES:
            raise ValueError(f"unknown move {move!r}; known: {', '.join(MOVES)}")
        if ease not in rp.EASES:
            raise ValueError(f"unknown ease {ease!r}; known: {', '.join(rp.EASES)}")
        img = (image[0].cpu().numpy().clip(0, 1) * 255 + 0.5).astype(np.uint8)[..., :3]
        d = depth[0].cpu().numpy()
        d = d[..., 0] if d.ndim == 3 else d
        d = rp.fit_depth(d, img)
        h, w = img.shape[:2]
        bbox = (bbox_x0 * w, bbox_y0 * h, bbox_x1 * w, bbox_y1 * h)
        if move.startswith("dolly_zoom"):
            frames, masks = rp.move_dolly_zoom(
                img, d, n_frames, bbox, 0.6 * intensity, "in" if move.endswith("in") else "out", ease
            )
        elif move == "crash_zoom":
            frames, masks = rp.move_crash_zoom(img, d, n_frames, bbox, 1.0 + 4.0 * intensity, ease)
        else:
            sign = 1.0 if move == "push_in" else -1.0
            frames, masks = rp.move_push(img, d, n_frames, sign * 0.6 * intensity, ease)
        if fill_holes:
            frames = np.stack([rp.fill_holes(f, m) for f, m in zip(frames, masks)])
        return (
            torch.from_numpy(np.ascontiguousarray(frames)).to(torch.float32).div_(255.0),
            torch.from_numpy(masks.astype(np.float32) / 255.0),
        )


NODE_CLASS_MAPPINGS = {"SGReprojectMove": SGReprojectMove}
NODE_DISPLAY_NAME_MAPPINGS = {"SGReprojectMove": "SG Reproject Move"}
