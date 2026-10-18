# Contributing to OPEN SAUCE

Thanks for looking. This file is the short version of how the repository is laid out, how changes are checked, and what a good pull request looks like.

## Layout

| Path | What it is |
|---|---|
| `custom_nodes/shotgrammar/` | The ShotGrammar node pack. Pure functions in modules, thin ComfyUI wrappers in `nodes_*.py`, tests in `tests/` that run without ComfyUI. |
| `workflows/` | API-format ComfyUI graphs. `_base_*.api.json` is the shared LTX-2.5 image-to-video pipeline; `_stage_*.api.json` are the still-image stages; `app/*.app.json` are the App Mode apps. |
| `presets/` | One JSON per preset: the prompt module, parameter pack, `run_steps` for multi-stage chains, input requirements, known issues. Presets are data; logic belongs in a node. |
| `app/` | `python -m app render|menu|fork|trailer`, driving ComfyUI through the official Comfy SDK. |
| `scripts/` | Rendering, validation, golden reproduction, install, capture and asset generators. |
| `examples/` | Golden inputs, locked seeds and the expected renders per preset. |
| `recipes/` | Fork This Shot recipe sidecars. Every rendered MP4 links to one of these by id. |
| `docs/` | Stack pins, App Mode notes, Comfy platform notes, verification logs. |

## Setup

Follow the Quickstart in the README. Development needs the same ComfyUI install plus:

```bash
pip install -r custom_nodes/shotgrammar/requirements.txt pytest ruff
```

## Quality gates

Every pull request must pass the three gates CI runs:

```bash
ruff check custom_nodes/shotgrammar scripts app tests
python scripts/validate_workflows.py
pytest
```

A change to a preset or a workflow must also keep its goldens: `python scripts/render_goldens.py --preset <name>` reproduces the expected renders at the locked seeds.

## Conventions

- Node classes follow the ComfyUI pattern (`INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`, `CATEGORY = "ShotGrammar"`) and are registered in `custom_nodes/shotgrammar/__init__.py`.
- Keep the math in a plain module and test it there. Wrappers only convert tensors.
- Workflow nodes the app patches are titled `OS:<role>` (`OS:image`, `OS:prompt`, `OS:seed`, `OS:save`, ...). `scripts/validate_workflows.py` checks the titles each preset needs.
- LTX frame counts are 8k+1; resolutions are multiples of 32.
- Pin the seed while iterating on anything other than the seed.
- Only open-weights models with licenses listed in `MODELS.md`. No API nodes, no hosted routers in the default path.
- No cross-dissolves, no fades to black, no end-image guides a camera could not physically reach. Motion is geometry first; the video model refines it.

## Pull requests

- One change per PR, with the gate output in the description.
- For visual changes attach a frame strip (`python scripts/observe_video.py <mp4> --out <dir> --n 16`) of before and after.
- Update `CHANGELOG.md` under *Unreleased*.

## Licensing

Code is MIT. Example inputs are Lightbrush-owned AI stills or CC0. Model weights are not redistributed; see `MODELS.md` for each license.
