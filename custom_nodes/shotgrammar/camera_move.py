"""Camera move registry and directives. Pure python (+PyYAML), no ComfyUI imports.

A directive bundles everything a graph needs for one named move: LTX prompt + negative,
SGReprojectMove settings scaled by intensity, SGSpeedRamp settings, duration and lane.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).with_name("moves.yaml")
LOCKED_FRAMING = {"static_hold", "levitate", "petrify"}  # prompts that promise unchanged framing

_cache: dict | None = None


def load_registry(path: str | Path | None = None) -> dict:
    """Return {name: move dict}. The default registry is cached; pass a path to load another."""
    global _cache
    if path is None and _cache is not None:
        return _cache
    with open(path or REGISTRY_PATH, encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    if not isinstance(reg, dict) or not reg:
        raise ValueError("moves registry is empty")
    if path is None:
        _cache = reg
    return reg


def app_move_names(registry=None):
    """Moves the single-graph hub app can honour (moves.yaml `app: true`)."""
    reg = registry or load_registry()
    moves = reg["moves"] if isinstance(reg, dict) and "moves" in reg else reg
    return [k for k, v in moves.items() if isinstance(v, dict) and v.get("app")]


def move_names() -> list[str]:
    return list(load_registry())


def _get(move: str) -> dict:
    reg = load_registry()
    if move not in reg:
        raise ValueError(f"unknown move {move!r}; known: {', '.join(reg)}")
    return reg[move]


def _frag(text: str) -> str:
    return text.strip().rstrip(".,; ")


def _join_unique(*lists) -> list[str]:
    seen, out = set(), []
    for lst in lists:
        for t in lst:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _as_list(v) -> list[str]:
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


def _reproject(spec: dict | None, intensity: float, bbox=None) -> dict | None:
    if spec is None:
        return None
    lo, hi = spec["intensity_range"]
    return {
        "move": spec["move"],
        "intensity": round(lo + (hi - lo) * intensity, 4),
        "ease": spec["ease"],
        "bbox": list(bbox or spec["bbox"] or [0.3, 0.3, 0.7, 0.7]),
        "bbox_hint": spec.get("bbox_hint"),
        "hole_mask_grow_px": spec.get("hole_mask_grow_px", 12),
    }


def _check_intensity(intensity: float) -> float:
    if not 0.0 <= intensity <= 1.0:
        raise ValueError(f"intensity must be in [0, 1], got {intensity}")
    return float(intensity)


def directive(move: str, intensity: float = 0.5, subject: str = "person", extras: dict | None = None) -> dict:
    """Directive for one move.

    extras (all optional): prompt (str|list appended), negative (str|list appended),
    seconds (override duration), bbox ([x0,y0,x1,y1] for the reproject target).
    """
    m = _get(move)
    intensity = _check_intensity(intensity)
    extras = extras or {}
    tokens = list(m["prompt_tokens"])
    for bound, phrase in m.get("intensity_tokens", []):
        if intensity <= bound:
            tokens.insert(2, phrase)  # before the identity-lock fragments
            break
    tokens += _as_list(extras.get("prompt"))
    prompt = ", ".join(_frag(t) for t in tokens).replace("{subject}", subject)
    negative = ", ".join(_join_unique(m["negative_tokens"], _as_list(extras.get("negative"))))
    return {
        "move": move,
        "stacked": False,
        "prompt": prompt,
        "negative": negative,
        "reproject": _reproject(m["reproject"], intensity, extras.get("bbox")),
        "stage": m.get("stage"),
        "ramp": dict(m["ramp"]),
        "seconds": float(extras.get("seconds", m["default_seconds"])),
        "lane": m["lane"],
        "intensity": intensity,
        "validate": m.get("validate"),
        "warnings": [],
    }


def stack(
    move_a: str,
    move_b: str,
    split: float = 0.5,
    intensity: float = 0.5,
    subject: str = "person",
    extras: dict | None = None,
    intensity_b: float | None = None,
    total_seconds: float | None = None,
) -> dict:
    """Two moves back to back. `split` is the fraction of total time given to move_a.

    Without total_seconds the total is the mean of the two default durations. The top-level
    prompt/negative/reproject/ramp/lane describe the whole stack (reproject and ramp come from
    the first half that has them); per-half values are under *_a / *_b.
    """
    if not 0.05 <= split <= 0.95:
        raise ValueError(f"split must be in [0.05, 0.95], got {split}")
    da = directive(move_a, intensity, subject, extras)
    db = directive(move_b, intensity if intensity_b is None else intensity_b, subject, extras)
    total = float(total_seconds) if total_seconds else (da["seconds"] + db["seconds"]) / 2.0
    if total <= 0:
        raise ValueError("total_seconds must be positive")
    seconds_a = round(total * split, 4)
    seconds_b = round(total - seconds_a, 4)
    warnings = []
    if move_a == move_b:
        warnings.append(f"both halves are {move_a}")
    for first, second in ((move_a, move_b), (move_b, move_a)):
        if first in LOCKED_FRAMING and second not in LOCKED_FRAMING:
            warnings.append(
                f"{first} promises 'the framing never changes' but is stacked with {second}: "
                "prompts conflict, validate on frames"
            )
    lane = da["lane"] if da["lane"] == db["lane"] else "mixed"
    return {
        "move": f"{move_a}+{move_b}",
        "stacked": True,
        "move_a": move_a,
        "move_b": move_b,
        "split": split,
        "seconds_a": seconds_a,
        "seconds_b": seconds_b,
        "seconds": round(total, 4),
        "prompt": f"{_frag(da['prompt'])}. Then {_frag(db['prompt'])}",
        "prompt_a": da["prompt"],
        "prompt_b": db["prompt"],
        "negative": ", ".join(_join_unique(da["negative"].split(", "), db["negative"].split(", "))),
        "reproject": da["reproject"] or db["reproject"],
        "reproject_a": da["reproject"],
        "reproject_b": db["reproject"],
        "stage": [s for s in (da["stage"], db["stage"]) if s],
        "ramp": da["ramp"],
        "ramp_a": da["ramp"],
        "ramp_b": db["ramp"],
        "lane": lane,
        "intensity": da["intensity"],
        "validate": [v for v in (da["validate"], db["validate"]) if v],
        "warnings": warnings,
    }


def directive_json(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False)
