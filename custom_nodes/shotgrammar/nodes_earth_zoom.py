"""ComfyUI wrapper for shotgrammar.earth_zoom. Imports cleanly without ComfyUI."""
from __future__ import annotations

import json

import numpy as np

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from . import earth_zoom as ez
    from .reproject import EASES
except ImportError:  # loaded as a plain module (tests, scripts)
    import earth_zoom as ez
    from reproject import EASES


class SGEarthZoomPath:
    @classmethod
    def INPUT_TYPES(cls):
        def f(default):
            return ("FLOAT", {"default": default, "min": 0.0, "max": 1.0, "step": 0.001})

        return {
            "required": {
                "inner": ("IMAGE",),
                "outer": ("IMAGE",),
                "inner_x0": f(0.25),
                "inner_y0": f(0.25),
                "inner_x1": f(0.75),
                "inner_y1": f(0.75),
                "n_frames": ("INT", {"default": 97, "min": 2, "max": 257}),
                "ease": (list(EASES),),
                "feather": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 16.0, "step": 0.5}),  # px
                "fade_end": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 1.0, "step": 0.01}),
            },
            # subject mattes of inner/outer (e.g. BiRefNet): when both are given the plates are made
            # to agree (outer subject inpainted, inner subject pasted) so no frame mixes two scenes
            # auto_inner_rect: measure where the inner subject landed in the outer still (multi-scale template
            # match on the subject matte); falls back to the manual rect below MIN_CONFIDENCE
            "optional": {"inner_subject_mask": ("MASK",), "outer_subject_mask": ("MASK",),
                         "auto_inner_rect": ("BOOLEAN", {"default": True})},
        }

    MIN_CONFIDENCE = 0.4

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("frames", "rect_json")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, inner, outer, inner_x0, inner_y0, inner_x1, inner_y1, n_frames, ease, feather=3.0, fade_end=0.5,
            inner_subject_mask=None, outer_subject_mask=None, auto_inner_rect=True):
        def u8(t):
            return (t[0].cpu().numpy().clip(0, 1) * 255 + 0.5).astype(np.uint8)[..., :3]

        rect = (inner_x0, inner_y0, inner_x1, inner_y1)
        a, b = u8(inner), u8(outer)
        info = {"mode": "manual", "rect": [round(float(v), 4) for v in rect]}
        if auto_inner_rect:
            m = inner_subject_mask[0].cpu().numpy() if inner_subject_mask is not None else None
            measured, conf = ez.measure_inner_rect(a, b, mask=m)
            info["measured"] = [round(float(v), 4) for v in measured]
            info["confidence"] = round(conf, 3)
            if conf >= self.MIN_CONFIDENCE:
                rect, info["mode"], info["rect"] = measured, "auto", info["measured"]
            print(f"[SGEarthZoomPath] inner_rect {info['mode']}: {info['rect']} (confidence {conf:.3f})")
        if inner_subject_mask is not None and outer_subject_mask is not None:
            a, b = ez.subject_plates(a, b, rect, inner_subject_mask[0].cpu().numpy(),
                                     outer_subject_mask[0].cpu().numpy(), feather)
        frames = ez.zoom_path(a, b, rect, n_frames, ease, feather, fade_end)
        # one float32 copy, not two (astype + divide): 97x1088x1920x3 is 2.3 GiB per copy
        return (torch.from_numpy(np.ascontiguousarray(frames)).to(torch.float32).div_(255.0), json.dumps({"inner_rect": info}))


class SGEarthZoomPyramid:
    """One continuous zoom through a nested plate stack: plate_0 (the photo) -> plate_1 (its outpaint) -> ... ->
    the coarsest plate. Each plate must have been generated FROM the previous one; rects_json gives where each
    plate_{k-1} sits inside plate_k ([[x0, y0, x1, y1], ...], normalised) or "auto" to measure them by template
    match (shrink_hint = the per-level shrink used by the outpaint stage, levels >= 2). Every output pixel comes from
    exactly one plate (<= feather px edge band); nothing is dissolved or cross-faded."""

    MAX_PLATES = 7

    @classmethod
    def INPUT_TYPES(cls):
        opt = {f"plate_{i}": ("IMAGE",) for i in range(1, cls.MAX_PLATES)}
        opt.update({"plate0_subject_mask": ("MASK",), "plate1_subject_mask": ("MASK",)})
        return {
            "required": {
                "plate_0": ("IMAGE",),
                "rects_json": ("STRING", {"default": "auto", "multiline": True}),
                "n_frames": ("INT", {"default": 241, "min": 2, "max": 513}),
                "ease_in": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01}),
                "feather": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 16.0, "step": 0.5}),  # px
                "shrink_hint": ("FLOAT", {"default": 0.375, "min": 0.05, "max": 0.95, "step": 0.005}),
                "min_confidence": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            # tone_match: grade plate_{k-1} (k >= 2) to plate_k's own re-render of it (smooth gain field, no blend)
            # subject mattes of plate_0 / plate_1 (BiRefNet): level 1 is a free re-render around the subject, so
            # the two plates are made to agree with subject_plates (as SGEarthZoomPath does) before nesting
            # only_frames: e.g. "0,24,...,240": output just those frames (in that order) instead of all n_frames, for
            # graphs that only take guide keys from the path (a 1088x1920x241 float batch is ~6 GB of host RAM)
            "optional": {**opt, "tone_match": ("BOOLEAN", {"default": True}),
                         "only_frames": ("STRING", {"default": ""})},
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("frames", "rects_json")
    FUNCTION = "run"
    CATEGORY = "ShotGrammar"

    def run(self, plate_0, rects_json, n_frames, ease_in, feather, shrink_hint, min_confidence,
            plate0_subject_mask=None, plate1_subject_mask=None, tone_match=True, only_frames="", **plates):
        def u8(t):
            return (t[0].cpu().numpy().clip(0, 1) * 255 + 0.5).astype(np.uint8)[..., :3]

        imgs = [u8(plate_0)]
        for i in range(1, self.MAX_PLATES):
            t = plates.get(f"plate_{i}")
            if t is None:
                break
            imgs.append(u8(t))
        if len(imgs) < 2:
            raise ValueError("SGEarthZoomPyramid needs plate_0 and at least plate_1")
        h, w = imgs[-1].shape[:2]
        imgs = [p if p.shape[:2] == (h, w) else ez.cv2.resize(p, (w, h), interpolation=ez.cv2.INTER_AREA) for p in imgs]
        if isinstance(rects_json, (list, tuple)):  # run_workflow --set parses JSON values before they reach the node
            given = list(rects_json)
        elif str(rects_json).strip().lower() in ("", "auto"):
            given = None
        else:
            try:
                given = json.loads(rects_json)
            except json.JSONDecodeError:  # str() of a Python list (None instead of null)
                import ast
                given = ast.literal_eval(str(rects_json))
        info, rects = [], []
        m0 = plate0_subject_mask[0].cpu().numpy() if plate0_subject_mask is not None else None
        for k in range(1, len(imgs)):
            # Qwen re-renders the canvas freely and may shrink the pasted inset far below shrink_hint (a 0.31 paste
            # came back at 0.14): sweep wide and fine for levels >= 2
            hint, steps = ((0.1, 0.55), 31) if k == 1 else ((0.05, min(shrink_hint * 1.4, 0.95)), 31)
            measured, conf = ez.measure_inner_rect(imgs[k - 1], imgs[k], scale_hint=hint, mask=m0 if k == 1 else None,
                                                   coarse_steps=steps)
            entry = {"level": k, "measured": [round(float(v), 4) for v in measured], "confidence": round(conf, 3)}
            if given is not None and k - 1 < len(given) and given[k - 1]:
                rect, entry["mode"] = tuple(float(v) for v in given[k - 1]), "given"
            elif conf >= min_confidence:
                rect, entry["mode"] = measured, "auto"
            else:
                s = shrink_hint if k > 1 else 0.5
                rect, entry["mode"] = ((1 - s) / 2, (1 - s) / 2, (1 + s) / 2, (1 + s) / 2), "fallback_centred"
            entry["rect"] = [round(float(v), 4) for v in rect]
            entry["edge_score"] = round(ez.edge_score(imgs[k], rect), 2)
            entry["scale"] = round(1.0 / (rect[2] - rect[0]), 2)
            print(f"[SGEarthZoomPyramid] level {k}: {entry}")
            info.append(entry)
            rects.append(rect)
        if tone_match:  # top-down, so each grade sees an already graded parent; level 1 (the hero) is never graded
            for k in range(len(imgs) - 1, 1, -1):
                imgs[k - 1] = ez.match_tone(imgs[k - 1], imgs[k], rects[k - 1])
        if m0 is not None and plate1_subject_mask is not None:
            imgs[0], imgs[1] = ez.subject_plates(imgs[0], imgs[1], rects[0], m0, plate1_subject_mask[0].cpu().numpy(), feather)
        only = [int(x) for x in str(only_frames).replace(" ", "").split(",") if x] or None
        frames, pmap = ez.zoom_pyramid(imgs, rects, n_frames, ease_in, feather, return_map=True, only=only)
        honesty = ez.honesty_check(pmap, feather)
        del pmap
        print(f"[SGEarthZoomPyramid] honesty check: {honesty}")
        if only:
            honesty["frames_checked"] = only
        out = {"levels": info, "switch_frames": ez.segment_switch_frames(rects, n_frames, ease_in),
               "total_scale": round(float(np.prod([e["scale"] for e in info])), 1), "honesty": honesty}
        return (torch.from_numpy(np.ascontiguousarray(frames)).to(torch.float32).div_(255.0), json.dumps(out))


NODE_CLASS_MAPPINGS = {"SGEarthZoomPath": SGEarthZoomPath, "SGEarthZoomPyramid": SGEarthZoomPyramid}
NODE_DISPLAY_NAME_MAPPINGS = {"SGEarthZoomPath": "SG Earth Zoom Path", "SGEarthZoomPyramid": "SG Earth Zoom Pyramid"}
