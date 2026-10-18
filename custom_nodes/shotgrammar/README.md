# ShotGrammar (MIT)

ComfyUI node pack for OPEN SAUCE.

## Nodes
- **SG Recipe Embed** (`SGRecipeEmbed`): takes an IMAGE batch plus preset, seed, models and extra JSON. Optionally (`burn_qr`, off by default) burns a QR code linking to the recipe into the bottom-right of the last 12 frames; always writes `recipes/<id>.json` and a recipe card PNG under `<output>/opensauce/`, and returns the frames, the recipe JSON and the recipe id.
- **SG Recipe Read** (`SGRecipeRead`): takes an MP4 path and returns the recipe JSON stored in its metadata (or the sidecar if metadata was stripped).
- **SG Reproject Move** (`SGReprojectMove`): depth-based camera move (dolly zoom, crash zoom, push/pull) from one image plus depth; returns frames and a hole mask.
- **SG Speed Ramp** (`SGSpeedRamp`): remaps frame timing with a curve (`linear`, `slow_mo_settle`, `speed_up`, `impact` with `hit_at`). Same frame count unless `out_frames` > 0; `blend` toggles neighbour blending.
- **SG Grade Chip** (`SGGradeChip`): deterministic look chips (`warm_film`, `cool_steel`, `bleach_bypass`, `teal_orange`, `vhs`, `super8`) plus seeded film grain.
- **SG Title Card** (`SGTitleCard`): fades a title/subtitle in over the first frame (image never fades), returns the held batch and a 2:3 poster.
- **SG Camera Move** (`SGCameraMove`): named move from `moves.yaml` (static_hold, levitate, jib_up, dolly_zoom_out/in, crash_zoom, push_in, pull_back, earth_zoom, petrify) to a directive: LTX `prompt`/`negative`, `directive_json`, plus `reproject_intensity`/`reproject_move` (`none` for prompt-led moves) and `ramp_curve`/`hit_at` to wire into SGReprojectMove and SGSpeedRamp. Also `move`, `reproject_ease`, `bbox_x0..bbox_y1` and `hole_grow` (for GrowMask). Feed the STRING outputs into SGReprojectMove `move_override`/`ease_override` and SGSpeedRamp `curve_override`: combos refuse STRING links. `second_move` + `split` stacks two moves with an explicit time split (per-half seconds, prompts and ramps are in the JSON).

Pure helpers live in `recipe.py`. MP4 metadata embedding and restore are also available from the CLI: `python scripts/fork_this_shot.py <video.mp4>` and `python scripts/fork_this_shot.py --embed <video.mp4> --recipe <json>`.

## Install
Copy or symlink this folder into `ComfyUI/custom_nodes/`, then `pip install qrcode pillow numpy mutagen imageio-ffmpeg`. ffmpeg is resolved from `imageio_ffmpeg` or `PATH`.

## Test
`python -m pytest -q custom_nodes/shotgrammar/tests` (no ComfyUI needed).
