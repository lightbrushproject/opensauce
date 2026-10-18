# OPEN SAUCE: Comfy Developer Platform notes (2026-10-16)

## What the SDK path actually exercised
`python -m app render levitate --image examples/levitate/input_01.jpg --seed 11` ran once, end to end, through
`comfy-sdk 0.5.0` -> `comfy-api-proxy 0.1.6` (http://127.0.0.1:8190) -> clean ComfyUI v0.41.2 (http://127.0.0.1:8189).
`scripts/start_proxy.ps1` was used as is.

| step | SDK call | result |
|---|---|---|
| graph in | `client.workflows.from_json(patched_graph)` | OK |
| image upload | `client.assets.from_file(jpg)` then `wf.set_input(node, "image", asset)` | OK through the proxy, no fallback needed |
| submit + wait | `client.run(wf, timeout=...)` | OK, job reached success |
| download | `job.get_outputs(save_node_id)` then `output.to_file(path)` | OK, `outputs/levitate/levitate_11.mp4` (704x1280, 97 frames) |

**No proxy route was missing for the render itself, so there is no raw-HTTP fallback in the render path.**

Two things the SDK does not cover, handled in `app/opensauce.py`:
1. **Recipe sidecar fetch (raw ComfyUI HTTP).** The `SGRecipeEmbed` node inside the graph burns the QR and writes the recipe
   JSON into ComfyUI's own `output/opensauce/recipes/`. The SDK/proxy has no route for that file, so `fetch_server_recipe`
   does one `GET {COMFYUI_URL}/view?filename=<id>.json&subfolder=opensauce/recipes&type=output` (default `http://127.0.0.1:8189`)
   so the MP4 tag, the `recipes/` sidecar and the QR all carry the same recipe id. If that fetch fails (for example against Comfy
   Cloud) the app builds the recipe locally; the id then differs from the burned QR and the output line says so.
2. **SDK mutates its input.** `from_json` + `set_input` change the dict you pass in (the asset object lands inside it), so the app
   deep-copies the graph first; the first attempt crashed at the recipe step on `deepcopy` of the SDK's lock object (fixed).

Levitate's preset pointed at the LTX-2.3 base; it now points at `workflows/_base_ltx25_i2v.api.json` (the goldens were 2.5).
Base workflows have no Fork This Shot node, so the app splices `SGRecipeEmbed` between the decode and `CreateVideo` at submit time.

Observed output (`scripts/observe_video.py`, strip at `tmp/obs/levitate_11_recipe/strip.png`): subject rises about a body height
over 97 frames, glow, shirt text and face hold, no black frames (mean brightness 109 -> 98), QR burned bottom-right at f96.
`python -m app fork outputs/levitate/levitate_11_recipe.mp4` restored recipe `b631261da8` and the API workflow from the MP4 tags.
Known gap: the recipe in that proof file has empty `inputs`/`models` because the proof render ran before `ensure_recipe_node`
was taught to fill them (the code now does; new renders carry them). Petrify and Pull Back (earth_zoom) are now
driven through `run_steps` (see below).

### Two-step presets (`run_steps`)
A preset lists steps; every step but the last is an image stage (`OS:save_still` output) whose still feeds the next step's named
`OS:*` LoadImage (`images: {"OS:image_end": "<stage name>"}`). The last step's MP4 is stamped as usual and its recipe `extra.stages`
lists `{step, recipe, still}`; each stage also gets its own recipe sidecar (`<preset>:<step>`). The SDK path works for stage upload and
download; `auto_runner` falls back to raw HTTP (`run_workflow.py` against :8189) only if the SDK path raises. SDK outputs carry no
filename, so files are named `<prefix>_<node id><ext from content type>`. Proofs (seed 11, 704x1280, via the proxy): petrify
`outputs/petrify/petrify_11_37_recipe.mp4` (reads as the golden: stone sets in from the feet, dust shroud, statue by f72), pull_back
`outputs/pull_back/pull_back_11_37_recipe.mp4`.
Seam caveat: the stage's Qwen still is a fresh render, so the hard-coded golden `inner_rect` misaligned on new photos (a plate
seam crossed the arch f0-f72). `SGEarthZoomPath` now has `auto_inner_rect` (default true): `earth_zoom.measure_inner_rect` template-matches
the input's subject (BiRefNet matte, gray + gradient NCC, scale sweep 0.2-0.55) inside the still; below confidence 0.4 it falls back to the
manual rect. The measured rect and confidence are recorded in the recipe `extra.inner_rect` (via the node's `rect_json` output into
`SGRecipeEmbed.extra_json_in`). Proofs (strips in `tmp/obs/app_pullback/strip_g03.png`, `strip_g01.png`): input_03 seed 33 rect
[0.3849, 0.4484, 0.6193, 0.6828] conf 0.752, clean, no plate seam, no ghost; input_01 seed 11: the first fresh still carried a Qwen-drawn straight arch-top edge (rect [0.402, 0.5625, 0.5824, 0.743] conf 0.777), so the zoom_out prompt now
adds "any rock arch or overhang curves overhead and continues naturally out of frame in every direction: no horizontal lines, no flat bridge, no straight edges"
(presets/earth_zoom.json, seed unchanged). Re-render (strip `tmp/obs/app_pullback/strip_g01_v2.png`): rect [0.4119, 0.5398, 0.5824, 0.7109] conf 0.826,
no plate seam, no horizontal edge, no ghost, subject leaves cleanly; f96 = still with a curved arch.

## comfy build (offline only; nothing was pushed)
`comfy build init <comfy-install> --name open-sauce --python <venv python> --comfy-url http://127.0.0.1:8189`
(added `--comfy-url` so it read the version from 8189, not the default 8188). Exit 0. Found:
- `baseComfyVersion: v0.41.2` (detected), environment Windows/AMD64, Python 3.14.2, torch 2.10.0+cu130.
- **1 model**: `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` (995,743,560 B). The real weights live outside `models/`
  (`extra_model_paths.yaml` -> external model roots), and init only scans `models/`, so the other ~100 GB are not in the spec.
  `push --dry-run`: `upload_count 1`, `upload_bytes 995743560` (upper bound; the builder may fetch it publicly by digest instead).
- **7 custom nodes**: six git packs with repo + commit (GGUF, LTXVideo, Manager, VideoHelperSuite, BiRefNet_ll, controlnet_aux),
  matching `docs/stack.md` / `MODELS.md`. **`shotgrammar` was recorded as a registry pack** (`id: shotgrammar`, `registryVersion: 0.1.0`,
  from our pyproject) because it is a symlink into this repo. Two consequences: packaging skips symlinks, and a push will ask the registry
  for a pin and probably fail with `build_registry_pin_missing`. Not tested (needs sign-in). Workaround options: publish
  ShotGrammar to the Comfy registry (our pyproject already has `[tool.comfy]`), or replace the entry with a `git` source once the
  GitHub repo is public.
- `pipDependencies`: init captured a 630-line Windows/py3.14 freeze. Per the `comfy-build` skill it was **emptied for the first cut**
  (comment-only block); the original is kept at `tmp/comfy-build.init-original.yaml` (not committed).
- Other warnings: none. `validate` OK (offline). `push --dry-run` OK.

The root `comfy-build.yaml` is a copy of `<comfy-install>\comfy-build.yaml` (`id: null`, `syncedRevision: null`: never pushed).

## Steps that need the account owner
1. `comfy cloud login` (browser sign-in; agents must not do it).
2. Decide `shotgrammar` (registry publish vs git source; see above) and the model plan (the spec holds only the 1 GB upscaler;
   the LTX-2.5 weights are gated and cannot be uploaded from a public build).
3. `comfy build push <comfy-install>` (after reviewing `--dry-run`).
4. `comfy build release create <comfy-install> --target linux/nvidia --watch`. The skill says to confirm the target list
   with `comfy build refs build-targets` first, and the release policy (models/partner nodes permitted) cannot be changed after the cut.
   Whether a Windows-authored spec cuts cleanly is unverified.
5. Do not `comfy deploy up` (billing starts at deploy).
6. App Mode / Hub app (UI work in the Comfy frontend; no manifest format is documented, see PLATFORM-RESEARCH.md Q1).
7. Gated LTX-2.5 access on any fresh machine: click "Agree and access" at https://huggingface.co/Lightricks/LTX-2.5.

## Installer status
`scripts/install.ps1` and `scripts/install.sh` were dry-run only (`-DryRun` / `--dry-run` print every git, pip and link
command with the pins; the live install was not touched). They have not been run for real: that is the install test (docs/install-test.md).
Unverified: the `cu130` torch index URL and whether every pack's `requirements.txt` installs on a fresh Python 3.14
(on the dev box `pip install -r` of two packs tried to build numpy from source, so pack requirement failures are non-fatal).
