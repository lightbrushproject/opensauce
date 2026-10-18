# Render stack

The pinned environment OPEN SAUCE is developed and verified on. `scripts/install.ps1` / `scripts/install.sh` reproduce it; `MODELS.md` lists every model file with its license and hash.

Reference hardware: one NVIDIA RTX 5090 (32 GB), 64 GB RAM, Windows 11. A second machine (RTX 5090 Laptop, 24 GB) reproduced the install from the README alone (`docs/install-test.md`).

## ComfyUI

| item | value |
|---|---|
| ComfyUI | tag **v0.41.2**, commit `b53f77a74e21091cbdebfdf7b85fc80326932646` |
| port | 8189 (`scripts/start_comfy.ps1`), `comfy-api-proxy` on 8190 (`scripts/start_proxy.ps1`) |
| Python | 3.12+ (3.14 used in development), venv with `--system-site-packages` |
| torch | 2.10.0+cu130, torchvision 0.25.0, torchaudio 2.11.0 |
| frontend / templates | comfyui-frontend-package 1.55.17, comfyui-workflow-templates 0.11.86, comfy-kitchen 0.2.37, comfy-aimdo 0.5.6, av 19.0.1 |
| SDK | comfy-sdk 0.5.0, comfy-cli 1.22.0 |

Model locations are set in the install's `extra_model_paths.yaml`. Keep the weights on fast local storage: the first cold render from a USB disk spent twenty minutes streaming weights that take forty seconds from NVMe.

### Custom node packs (depth-1 clones, pinned)

| pack | commit | date | license | used for |
|---|---|---|---|---|
| ComfyUI-Manager | `4d3bed4b569205124a52444caf25de1719fae0de` | 2026-10-16 | GPL-3.0 | convenience only |
| ComfyUI-LTXVideo | `44c8a36b7c31ee00b4271daed11dc2a4aa481140` | 2026-10-14 | Apache-2.0 | not required by the shipped graphs |
| comfyui_controlnet_aux | `a587a4c1594524c1d2de5cd1a86cd868ff448e1c` | 2026-10-11 | Apache-2.0 | Depth Anything V2 ViT-S |
| ComfyUI-VideoHelperSuite | `4d907bee61e92c2e65af3bd6383a4e4d356126d1` | 2026-09-01 | GPL-3.0 | not required by the shipped graphs |
| city96/ComfyUI-GGUF | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` | 2026-01-12 | Apache-2.0 | `UnetLoaderGGUF` (Qwen-Image-Edit-2511 Q4_K_M) |
| lldacing/ComfyUI_BiRefNet_ll | `5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529` | 2025-06-02 | MIT | BiRefNet mattes (Petrify, Pull Back) |
| shotgrammar (this repo) | `custom_nodes/shotgrammar` | | MIT | camera moves, recipes, Fork This Shot |

The LTX pipeline itself uses only core ComfyUI nodes.

## Video model: LTX-2.5

LTX-2.5 (core-native since ComfyUI v0.32.0) is the only video model. `workflows/_base_ltx25_i2v.api.json` is the API conversion of the official `video_ltx2_5_i2v.json` template with a centre-crop resize added in front. The weights are gated on Hugging Face: accept the terms at https://huggingface.co/Lightricks/LTX-2.5, then `python scripts/download_ltx25.py`. Unofficial re-uploads are deliberately not used.

Pipeline shape, both LTX generations:

- Image: centre-crop resize to the target size, `LTXVPreprocess`.
- Stage 1 at half size, image-to-video in place, CFG 1, distilled sigmas.
- Latent spatial upsampler x2, then a short stage 2 at full size.
- Tiled VAE decode, `CreateVideo`, `SaveVideo` (H.264).
- Defaults: 704x1280 drafts, 1088x1920 / 1920x1088 finals, 97 frames at 24 fps (4.04 s), frame counts 8k+1, sizes multiples of 32 (multiples of 64 when stage 1 runs at half size).

LTX-2.3 (`workflows/_base_ltx_i2v.api.json`, nvfp4 transformer + distilled LoRA) is kept as a documented fallback. In a side-by-side on the Levitate golden, 2.5 held text, face and footwear and followed the camera prompt; 2.3 rendered a prettier stylised glow but drifted on text and face.

## Still-image stages

- **Qwen-Image-Edit-2511** (Q4_K_M GGUF, Apache-2.0): the Petrify stone pass and the Pull Back zoom-out plate. The stage mirrors the official `image_qwen_image_edit_2511.json` template (ModelSamplingAuraFlow 3.1, CFGNorm 1.0, KSampler cfg 4 euler/simple), without the Lightning LoRA and at the video size so it composites 1:1.
- **BiRefNet General** (MIT): subject mattes.
- **Depth Anything V2 ViT-S** (Apache-2.0): depth for `SGReprojectMove`. The ViT-L checkpoint is CC-BY-NC and is not used.

## Measured timings (RTX 5090, warm)

| step | time |
|---|---|
| LTX-2.5 I2V, 704x1280x97 | 39 s |
| LTX-2.5 I2V, 1088x1920x97 | 60–200 s |
| LTX-2.5 with 8 reprojection guides | 45–64 s |
| Qwen-Image-Edit stage, 30 steps, 704x1280 | 85–100 s (incl. cold loader) |
| BiRefNet matte | 3 s |
| Petrify chain end to end (stage + video, 1088x1920) | ~5.5 min |

## Gotchas

- `/system_stats` reports VRAM free for the whole card and can disagree with `nvidia-smi` when other apps hold memory. Trust `nvidia-smi`.
- The venv `python.exe` is a launcher: the process that owns port 8189 is its child. To stop the server, stop the port owner, then the launcher. Never stop Python processes by name.
- `scripts/run_workflow.py` exits on `/prompt` node errors. ComfyUI otherwise runs only the valid outputs and still reports success.
- `SGSpeedRamp`'s curve is `slow_mo_settle`; `SGReprojectMove`'s ease is `slowmo_settle`.
- Restart the server after any `extra_model_paths.yaml` change; it reads the file once at startup.
