"""ComfyUI wrapper for shotgrammar.camera_move. Imports cleanly without ComfyUI."""
from __future__ import annotations

try:
    from . import camera_move as cm
except ImportError:  # loaded as a plain module (tests, scripts)
    import camera_move as cm


class SGCameraMove:
    @classmethod
    def INPUT_TYPES(cls):
        names = cm.app_move_names()  # hub-app menu; other moves reach graphs via *_override strings
        return {
            "required": {
                "move": (names,),
                "intensity": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "subject": ("STRING", {"default": "person"}),
                "second_move": (["none"] + names,),
                "split": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 0.95, "step": 0.01}),
            }
        }

    # outputs 7+ were appended for the one-graph app (workflows/open_sauce.api.json); keep indices 0-6 stable
    RETURN_TYPES = (
        "STRING", "STRING", "STRING", "FLOAT", "STRING", "STRING", "FLOAT",
        "STRING", "STRING", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "INT",
    )
    RETURN_NAMES = (
        "prompt",
        "negative",
        "directive_json",
        "reproject_intensity",
        "reproject_move",
        "ramp_curve",
        "hit_at",
        "move",
        "reproject_ease",
        "bbox_x0",
        "bbox_y0",
        "bbox_x1",
        "bbox_y1",
        "hole_grow",
    )
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, move, intensity, subject, second_move, split):
        if second_move == "none":
            d = cm.directive(move, intensity, subject)
        else:
            d = cm.stack(move, second_move, split, intensity, subject)
        rp = d["reproject"]  # None for prompt-led moves -> intensity 0, move "none"
        bbox = rp["bbox"] if rp else [0.3, 0.3, 0.7, 0.7]
        return (
            d["prompt"],
            d["negative"],
            cm.directive_json(d),
            float(rp["intensity"]) if rp else 0.0,
            rp["move"] if rp else "none",
            d["ramp"]["curve"],
            float(d["ramp"].get("hit_at", 0.6)),
            d["move"],
            rp["ease"] if rp else "linear",
            *(float(v) for v in bbox),
            int(rp["hole_mask_grow_px"]) if rp else 12,
        )


NODE_CLASS_MAPPINGS = {"SGCameraMove": SGCameraMove}
NODE_DISPLAY_NAME_MAPPINGS = {"SGCameraMove": "SG Camera Move"}
