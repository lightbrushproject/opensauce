# Changelog

All notable changes to OPEN SAUCE. The format follows Keep a Changelog; versions follow SemVer.

## [Unreleased]

- Nothing yet.

## [0.1.0] - 2026-10-18

Initial public release.

### Presets
- Vertigo, Crash Zoom, Disintegrate, Petrify, Levitate and Main Character Trailer, all on one shared LTX-2.5 image-to-video pipeline. Pull Back is available as a camera move in the app and closes the trailer.
- Locked golden renders at 1088x1920 / 1920x1088 for every preset, reproducible with `scripts/render_goldens.py`.

### ShotGrammar node pack
- `SGCameraMove`: named camera moves from a registry (`moves.yaml`) to prompt tokens, reprojection parameters and timing.
- `SGReprojectMove`: depth-based z-buffer reprojection for crash zoom, dolly zoom and push moves, with hole filling.
- `SGEarthZoomPath`: two-plate geometric zoom with measured inner rectangle (the Pull Back move).
- `SGDisintegrate` / `SGRemovalMask`: opaque per-pixel disintegration guides with attention weights that pin the world to a clean plate, and the removal mask that makes that plate.
- `SGSpeedRamp`, `SGGradeChip`, `SGTitleCard`.
- `SGRecipeEmbed` / `SGRecipeRead` (Fork This Shot): the full recipe travels as MP4 metadata, sidecar JSON and recipe card; an optional end-frame QR (`burn_qr`, off by default) survives social re-encoding.
- LTX first-last-frame bridges and a continuous-take trailer assembler.

### App
- `python -m app render|menu|fork|trailer` on the official Comfy SDK through `comfy-api-proxy`.
- One ComfyUI App Mode app with a preset dropdown, plus per-preset apps.
- `comfy-build.yaml` for the Comfy API platform, built and released.

### Verification
- Open-weights audit: no API nodes, offline render proven.
- Cold install from the README on a second machine.
