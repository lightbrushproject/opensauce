# AGENTS.md

Guidance for coding agents and new contributors working in this repository. `CONTRIBUTING.md` has the longer version.

## What this is
One shared LTX-2.5 image-to-video pipeline (`workflows/_base_ltx25_i2v.api.json`). Each preset in `presets/` is a parameter pack over it plus at most one custom stage from `custom_nodes/shotgrammar`. `app/` submits graphs through the Comfy SDK. Every render emits MP4 + recipe JSON + recipe card + end-frame QR.

## Gates (run before every commit)
```bash
ruff check custom_nodes/shotgrammar scripts app tests
python scripts/validate_workflows.py
pytest
```

## Rules
- Pure functions in modules, thin node wrappers; tests target the functions and must not import ComfyUI.
- Presets are data. Logic a preset needs belongs in a node.
- Workflow nodes the app patches carry `OS:<role>` titles. Add new roles to `scripts/validate_workflows.py`.
- LTX frame counts 8k+1, resolutions multiples of 32. Pin seeds while iterating on anything else.
- Open weights only. Every model and its license goes in `MODELS.md`. No API nodes or hosted routers in the default path.
- Motion is geometry first; the video model refines it. No dissolves, no fades to black, no unreachable end-image guides.
- Verify visually: render, extract frames (`scripts/observe_video.py`), look at them, then report.
- Do not commit rendered outputs outside `examples/*/expected/`.
