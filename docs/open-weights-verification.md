# Open-weights verification: no API nodes, no network

Date: 2026-10-17. Machine: development workstation (RTX 5090 32 GB). ComfyUI v0.41.2 on port 8189. Tool: `python scripts/verify_clean_run.py [--render]`.

## 1. Static audit (PASS)
- 55 distinct class_types across `workflows/*.api.json`; **0** API/partner nodes. No class resolves to a `comfy_api_nodes.*` python_module (mapped through `/object_info` `python_module`), and none matches the denylist (Api, Partner, Router, Cloud, Openai, Gemini, Kling, Runway, Minimax, Luma, Pika, Veo, Ideogram, Recraft, Stability, BFL, ...).
- Node packs the graphs need: core ComfyUI (46 classes), `shotgrammar` (SGEarthZoomPath, SGGradeChip, SGRecipeEmbed, SGReprojectMove, SGSpeedRamp), ComfyUI-GGUF (UnetLoaderGGUF), ComfyUI_BiRefNet_ll (LoadRembgByBiRefNetModel, GetMaskByBiRefNet), comfyui_controlnet_aux (DepthAnythingV2Preprocessor). ComfyUI-Manager, ComfyUI-LTXVideo and VideoHelperSuite are NOT needed.
- Outbound-network scan of `custom_nodes/shotgrammar`, `app/`, `scripts/`: SGRecipeEmbed and the app make **no** remote calls. The only remote URLs are text: the recipe/QR base URL (`https://github.com/lightbrushproject/opensauce/blob/main/recipes/`, written into the QR and recipe JSON, never fetched). Every `urlopen` targets the local ComfyUI. `scripts/download_ltx25.py` (`hf_hub_download`) is an install-time model fetch, not part of any render.
- Third-party pack download code exists but is only reached when a model file is missing: comfyui_controlnet_aux auto-downloads Depth Anything ckpts, BiRefNet_ll has `AutoDownloadBiRefNetModel` (not in any graph). All files were already on disk.

## 2. Method used (NOT a firewall rule)
The session was not elevated, so the Windows Firewall outbound-block rule could not be created (no rule was created, nothing to remove). Fallback per plan:
- Server restarted (stopped only the PID listening on 8189 after checking its command line contained `main.py` and `8189`, queue empty), then started via `scripts/start_comfy.ps1` with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_PROXY=*`.
- Extra args `--disable-all-custom-nodes --whitelist-custom-nodes shotgrammar ComfyUI-GGUF ComfyUI_BiRefNet_ll comfyui_controlnet_aux`. Reason: with ComfyUI-Manager loaded, the server phones home at startup (`default cache updated: https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/...`, api.comfy.org). Manager is a dev-box convenience, not part of OPEN SAUCE, so it was excluded.
- A PowerShell watcher sampled every 1.5 s, for the whole render session, all TCP connections owned by the server PID and its launcher PID.
- Afterwards the server was restarted normally (Manager loaded again).

## 3. Offline renders (golden-1 seed 11, 704x1280, 97 frames @ 24 fps)
Outputs in `tmp/verify_clean_run/<preset>/` (gitignored scratch), strips in `tmp/verify_clean_run/strip_<preset>/strip.png`. Wall time covers every stage; levitate was first after restart so it includes cold model loads.

| preset | wall s | output | network observations |
|---|---|---|---|
| levitate | 37.7 | tmp/verify_clean_run/levitate/verify_levitate_00001_.mp4 | none |
| crash_zoom | 72.4 | tmp/verify_clean_run/crash_zoom/verify_crash_zoom_00001_.mp4 | none |
| vertigo | 84.7 | tmp/verify_clean_run/vertigo/verify_vertigo_00001_.mp4 | none |
| petrify (Qwen+BiRefNet stage, then video) | 150.7 | tmp/verify_clean_run/petrify/verify_petrify_00001_.mp4 | none |
| pull_back (Qwen zoom-out stage, then earth_zoom) | 168.8 | tmp/verify_clean_run/pull_back/verify_pull_back_00001_.mp4 | none |

Network evidence:
- 261 netstat samples over the session: **0** with a non-loopback remote address (only 127.0.0.1 client connections).
- Server stderr during the renders: **0** lines matching download / huggingface / http. Whole startup-to-end log has no download or huggingface lines (only xFormers / single-GPU warnings and the local GUI URL).
- Every preset produced an MP4; one strip per preset was read: levitate rises, crash_zoom pushes to the face with QR on the last frames, vertigo holds the subject while the canyon widens, petrify turns to grey stone with dust, pull_back shrinks the hero into a wider canyon.
- Caveat on pull_back: this was a smoke test. The Qwen zoom-out prompt was re-typed (the locked S1 still was not reused), so the generated plate has a visible horizontal seam across the cliff band in the strip. That is a content-quality issue for the Earth Zoom preset, not a network or node issue.

Limit of the evidence: without admin there is no kernel-level block, so this proves "no connection was attempted/observed", not "none could have succeeded". To harden, re-run from an elevated shell: `New-NetFirewallRule -DisplayName "opensauce-offline-test" -Direction Outbound -Program <comfy-install>\.venv\Scripts\python.exe -Action Block`, then `python scripts/verify_clean_run.py --render`, then `Remove-NetFirewallRule -DisplayName "opensauce-offline-test"`.

## 4. Wording
Typeform, "Is your stack fully open?":
> Yes, open weights only. OPEN SAUCE runs on LTX-2.5 (open weights, LTX community license), Qwen-Image-Edit-2511 (Apache-2.0), BiRefNet (MIT) and Depth Anything V2 Small (Apache-2.0), through plain ComfyUI core nodes plus our MIT ShotGrammar pack. There are no API or partner nodes in any workflow (checked by scripts/verify_clean_run.py), no paid services, and every shipped preset was rendered with open network access off the table (offline env, no outbound connections observed). Every model's version, license, URL and sha256 is in MODELS.md.

README:
> **Fully open stack.** Every preset runs locally on open-weight models (LTX-2.5, Qwen-Image-Edit-2511, BiRefNet, Depth Anything V2 Small) via ComfyUI core nodes and the MIT ShotGrammar pack. No API nodes, no cloud calls, no accounts at render time. Verify it yourself: `python scripts/verify_clean_run.py` (static audit) and `--render` (renders every preset). Models and licenses: MODELS.md. Note that LTX-2.5 uses the LTX community license (free under USD 10M annual revenue), which is open-weight but not OSI open source.

Do not claim "OSI open source" for the whole stack; LTX-2.5 and the Gemma-4 text encoder terms are license-restricted (see MODELS.md).
