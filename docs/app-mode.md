# App Mode apps (the "usable interface" the contest asks for)

ComfyUI's built-in **App Mode** (frontend 1.41+; our clean install runs 1.55) turns a workflow into a form: inputs on the right, Run, results at the bottom. Comfy's own example entries (Cinematic Studio, Re-shoot) are exactly this. Files whose name ends in `.app.json` open directly in App Mode.

## Files
| app | file | inputs exposed | output |
|---|---|---|---|
| **OPEN SAUCE (one app)** | `workflows/app/open_sauce.app.json` | photo, preset dropdown, intensity 0-1, seed, extra prompt | the MP4 (SaveVideo) |
| Levitate | `workflows/app/levitate.app.json` | photo (LoadImage), prompt text, seed | the MP4 (SaveVideo) |
| Crash Zoom | `workflows/app/crash_zoom.app.json` | photo, intensity (SG Reproject Move), seed | the MP4 |
| Vertigo | `workflows/app/vertigo.app.json` | photo, intensity, seed | the MP4 |

The three per-preset apps remain for reference; `open_sauce` replaces them as the shipped app.

How they were made: the API-format graph was loaded with the frontend's own importer (`app.loadApiJson`), the exposed controls were written to `extra.linearData = {inputs: [[nodeId, widgetName], …], outputs: [nodeId, …]}` with `extra.linearMode = true` (the structure the App Builder writes; see `useAppMode`/`appModeStore` in the frontend bundle), and the workflow was saved through the frontend's userdata API as `<name>.app.json`.

## The one app (`open_sauce`)
Source graph: `workflows/open_sauce.api.json` (90 nodes). App file rebuilt with
`python scripts/make_app_json.py workflows/open_sauce.api.json --name open_sauce --input 9:image --input 200:move --input 201:value --input 17:noise_seed --input 202:value --output 37`
(POSTs the API json to userdata as `workflows/_src_open_sauce.api.json`, then runs the frontend's `app.loadApiJson` in headless Chromium via Playwright, writes `extra.linearData`/`linearMode`, saves `workflows/open_sauce.app.json` to userdata and copies it to `workflows/app/`; without Playwright it prints the JS snippet to paste in the browser console).

| input (order) | node | notes |
|---|---|---|
| photo | 9 `LoadImage` OS:image | centre-cropped to 704x1280 |
| preset | 200 `SGCameraMove.move` OS:preset | the dropdown is the full `moves.yaml` list; the app's menu is `levitate`, `crash_zoom`, `dolly_zoom_out` (Vertigo), `push_in`, `pull_back`. V1 combos have no per-option display labels, so Vertigo shows as `dolly_zoom_out`. Other entries (static_hold, jib_up, dolly_zoom_in, earth_zoom, petrify) run but are unproven or need their CLI stage |
| intensity | 201 `PrimitiveFloat` OS:intensity -> SGCameraMove.intensity | 0..1 (PrimitiveFloat has no range clamp; SGCameraMove raises outside 0..1). Maps onto each move's `intensity_range` (crash 0.333 = shipped 0.5, Vertigo 0.857 = shipped 0.9) or picks the levitate intensity phrase |
| seed | 17 `RandomNoise` OS:seed | stage-1 noise; the prompt-led stage 2 keeps its own seed 42 as in the base graph. SGRecipeEmbed.seed is a widget (cannot be fed from NOISE); the true seed is in the recipe's `api_workflow` |
| extra prompt | 202 `PrimitiveStringMultiline` OS:extra | appended to the directive prompt by `StringConcatenate` (delimiter `. `); describe the subject here (glowing eyes, shirt print) or LTX-2.5 normalises it |

Routing: `SGCameraMove.reproject_move` -> `StringCompare(Equal, "none")` -> two `ComfySwitchNode`s (video latent, audio latent).
- true = prompt-led (levitate): the base two-stage I2V (`_base_ltx25_i2v`, nodes 111-133).
- false = geometry-led (crash_zoom, dolly_zoom_out, push_in, pull_back): DepthAnythingV2 -> SGReprojectMove -> 8 LTXVAddGuide keys with hole masks (crash_zoom graph).
ComfySwitchNode inputs are lazy: only the chosen branch's sampler (and the depth/reprojection stage) runs. Directive outputs also drive SGReprojectMove intensity/bbox/ease, GrowMask expand, SGSpeedRamp curve/hit_at, SGRecipeEmbed preset (+ `directive_json` as `extra_json`). `pull_back` here is SGReprojectMove `pull_out` + LTX; the Qwen-outpaint Pull Back (Earth Zoom style) stays CLI-only.

**STRING into a combo does not work.** ComfyUI 0.41.2 rejects a STRING link into a V1 combo at validation (`return_type_mismatch`); a node-side `VALIDATE_INPUTS(input_types)` gets past the server, but the frontend importer silently drops such links, so App Mode would run the widget value. Fix: SGReprojectMove has optional STRING inputs `move_override` / `ease_override` and SGSpeedRamp `curve_override` (`forceInput`); they win over the combo when linked.

Proof (seed 11, `examples/levitate/input_01.jpg`, 704x1280x97, strips in `tmp/obs/open_sauce/`): crash_zoom 78 s (hit by f19, holds a ~3x head-and-chest close-up), dolly_zoom_out 87 s (subject locked, arch and strata close in), levitate 36-39 s (rises, feet off the sand from f19). The App Mode file itself was round-tripped (`loadGraphData` -> set the 5 inputs -> `graphToPrompt` -> /prompt): no link differences vs the API graph and a dolly_zoom_out render identical to the API-graph render.

Known differences vs the per-preset graphs: levitate now gets the directive ramp `slow_mo_settle` (the base graph had no ramp); a long appended subject description made levitate dolly in (~2x); keep the extra prompt short.

## Use
1. Start ComfyUI (port 8189 in our setup) and open http://127.0.0.1:8189.
2. Workflows sidebar → open `OpenSauce Levitate` (copy the `.app.json` files into `<ComfyUI>/user/default/workflows/`, or drag one onto the canvas).
3. Pick a photo, optionally edit the prompt, press **Run**. The video appears in the results panel; its recipe is in the file; switch on the **burn_qr** toggle before Run to also stamp the Fork This Shot QR into the last half second.
4. "Graph" switches back to the node view; "Build an app" edits which controls are exposed.

## Not covered by App Mode
- Petrify and Disintegrate are two-stage (Qwen-Image-Edit still → LTX video). App Mode shows one graph at a time; the CLI `python -m app render` and `scripts/run_workflow.py` run the chain. A merged single-graph version is the next step.
- Share links from App Mode work on Comfy Cloud only, and our custom nodes are not on Cloud. A hosted "try it" link therefore means either a Comfy API deployment of `comfy-build.yaml` or a self-hosted tunnel to a local ComfyUI.


## Final hub file (2026-10-17 ~11:10)
`workflows/app/open_sauce.app.json` (saved on the dev server as `OPEN SAUCE.app.json`). Four controls: **image** (your photo), **move** (the preset dropdown from moves.yaml: levitate, crash_zoom, dolly_zoom_out = Vertigo, push_in, pull_back, …), **intensity** (0–1, on the SG Camera Move node), **noise_seed**. Output: the SaveVideo MP4 with the Fork This Shot QR. The extra-prompt primitive was removed from the exposed controls (fewer knobs; the preset owns the prompt). Proof: a crash_zoom run launched from this App Mode panel produced `open_sauce_00002_.mp4` (704x1280, 4 s) in the results panel; screenshots in docs/img/.
Note on labels: App Mode shows widget names; a third tuple element `{label}` in linearData is ignored by frontend 1.55, so control names come from the widgets themselves (hence `noise_seed`, not `Seed`). Renaming needs the App Builder UI or a frontend that supports labels.
