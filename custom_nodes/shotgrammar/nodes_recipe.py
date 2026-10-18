"""ComfyUI wrappers around recipe.py. Importable outside ComfyUI."""

import json
from pathlib import Path

try:
    import folder_paths
except ImportError:
    folder_paths = None

from . import recipe as R


def _output_root():
    base = folder_paths.get_output_directory() if folder_paths else "output"
    return Path(base) / "opensauce"


class SGRecipeEmbed:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "preset": ("STRING", {"default": "levitate"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "recipe_base_url": ("STRING", {"default": R.DEFAULT_BASE}),
                "models": ("STRING", {"default": "", "multiline": True}),
                "extra_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            # extra_json_in: JSON merged into extra (e.g. a node's measured values wired in)
            "optional": {
                "extra_json_in": ("STRING", {"default": "{}", "forceInput": True}),
                # opt-in: the recipe always travels in the MP4 metadata and the sidecar; the QR is a visible extra
                "burn_qr": ("BOOLEAN", {"default": False, "label_on": "QR in last frames", "label_off": "no QR"}),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "recipe_json", "recipe_id")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, images, preset, seed, recipe_base_url, models, extra_json, extra_json_in="{}", burn_qr=False,
            prompt=None):
        extra = json.loads(extra_json or "{}")
        extra.update(json.loads(extra_json_in or "{}"))
        inputs = extra.pop("inputs", [])
        model_list = [m.strip() for m in models.splitlines() if m.strip()]
        extra["base_url"] = recipe_base_url
        rec = R.build_recipe(preset, seed, inputs, model_list, prompt or {}, extra)
        root = _output_root()
        R.write_sidecar(rec, root / "recipes")
        R.render_recipe_card(rec, root / "cards" / f"{rec['id']}.png")
        if not burn_qr:
            return (images, json.dumps(rec), rec["id"])
        import torch  # only the QR path touches tensors

        burned = R.burn_endframe_qr(images.cpu().numpy(), R.recipe_url(rec, recipe_base_url))
        return (torch.from_numpy(burned), json.dumps(rec), rec["id"])


class SGRecipeRead:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("recipe_json",)
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, video_path):
        return (json.dumps(R.read_recipe_from_mp4(video_path, _output_root() / "recipes")),)


NODE_CLASS_MAPPINGS = {"SGRecipeEmbed": SGRecipeEmbed, "SGRecipeRead": SGRecipeRead}
NODE_DISPLAY_NAME_MAPPINGS = {"SGRecipeEmbed": "SG Recipe Embed", "SGRecipeRead": "SG Recipe Read"}
