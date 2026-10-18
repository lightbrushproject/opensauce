# MODELS

Every model file an OpenSauce workflow loads. Started 2026-10-16 with the Petrify stage models.
LTX-2.5 and Depth Anything rows were verified 2026-10-16 (sha256, size, license); see the Verification log at the end.

Model search order is set in `extra_model_paths.yaml` of the ComfyUI install (fast local storage first; see docs/stack.md).

| model | file (ComfyUI folder) | license | source URL | used by |
|---|---|---|---|---|
| Qwen-Image-Edit-2511, Q4_K_M GGUF quant by unsloth (HF revision `1daa38515d`, the pre-2026-01-08 upload; current main is a different file) | `diffusion_models/qwen-image-edit-2511-Q4_K_M.gguf` (13,127,088,736 B, sha256 `5f2ef6c0bf59e5a15aaf8836fcb07d9424f36dd0f1a62e285cd3055c7b374fca`) | Apache-2.0 (base model Qwen/Qwen-Image-Edit-2511) | https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/blob/1daa38515d/qwen-image-edit-2511-Q4_K_M.gguf | workflows/_stage_petrify_qwen.api.json (via ComfyUI-GGUF `UnetLoaderGGUF`), workflows/_stage_earth_zoom_outpaint.api.json |
| Qwen2.5-VL-7B text encoder, fp8 scaled (Comfy-Org repackage) | `text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` (sha256 `cb5636d852a0ea6a9075ab1bef496c0db7aef13c02350571e388aea959c5c0b4`) | Apache-2.0 (Qwen2.5-VL-7B-Instruct) | https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors | workflows/_stage_petrify_qwen.api.json, workflows/_stage_earth_zoom_outpaint.api.json |
| Qwen-Image VAE (Comfy-Org repackage) | `vae/qwen_image_vae.safetensors` (sha256 `a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f`) | Apache-2.0 | https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/vae/qwen_image_vae.safetensors | workflows/_stage_petrify_qwen.api.json, workflows/_stage_earth_zoom_outpaint.api.json |
| BiRefNet General (ZhengPeng7/BiRefNet, HF revision `e2bf8e4460`) | `BiRefNet/General.safetensors` (renamed from `model.safetensors`; 444,473,596 B, sha256 `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154`) | MIT | https://huggingface.co/ZhengPeng7/BiRefNet/resolve/e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4/model.safetensors | workflows/_stage_petrify_qwen.api.json (via ComfyUI_BiRefNet_ll) |
| LTX-2.5 distilled transformer int8 | `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` (21,504,034,224 B, sha256 `c4279eeff115cbeaca494bd2183e7d768c38fe85a184dc6afbb7159157c44334`) | LTX-2.x Community License Agreement (`ltx-2.x-community-license-agreement`, dated 2026-08-11): free for entities under USD 10M annual revenue; Commercial Entities (>= USD 10M) need a paid Commercial Use Agreement except for non-commercial purposes; derivatives carry the license; open-weight, not OSI | https://huggingface.co/Lightricks/LTX-2.5 | all presets |
| LTX-2.5 Gemma-4 12B text encoder + projection int8 | `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` (15,372,969,374 B, sha256 `6ce688a0aa98a5fa36a9f1e6c3f42152a498cc2b53ee8c15674c64244f91487f`) | LTX-2.x Community License Agreement (same as the transformer row; Gemma-4 terms not separately verified) | https://huggingface.co/Lightricks/LTX-2.5 | all presets |
| LTX-2.5 video VAE / audio VAE | `vae/ltx-2.5-video-vae-bf16.safetensors` (1,472,223,346 B, sha256 `847e14ca7f3355debca0cea4eaa24ac0fbcdf0061da054ac89ca638a869ddba3`), `vae/ltx-2.5-audio-vae-bf16.safetensors` (364,866,540 B, sha256 `c52733d37f6a7fb7949c3dc0fb468c6cb2169e4d836983a73babb9f0d54837a5`) | LTX-2.x Community License Agreement (same as the transformer row; no per-file license) | https://huggingface.co/Lightricks/LTX-2.5 | all presets |
| Depth Anything V2 ViT-S | `depth_anything_v2_vits.pth` (comfyui_controlnet_aux ckpts, auto-downloaded; 99,218,434 B, sha256 `715fade13be8f229f8a70cc02066f656f2423a59effd0579197bbf57860e1378`) | Apache-2.0 (verified 2026-10-16; the ViT-L variant is CC-BY-NC-4.0 and is NOT used; switched 2026-10-16, quality on crash_zoom g01 unchanged) | https://huggingface.co/depth-anything/Depth-Anything-V2-Small | crash_zoom, vertigo (not petrify) |

Explicitly NOT used: RMBG-2.0 (briaai, non-commercial license), Depth Anything V2 ViT-L (CC-BY-NC-4.0), FLUX.1 dev/fill (non-commercial).

## Node packs that load these models
| pack | commit | license |
|---|---|---|
| city96/ComfyUI-GGUF | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` (2026-01-12) | Apache-2.0 |
| lldacing/ComfyUI_BiRefNet_ll | `5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529` (2025-06-02) | MIT |

Pull Back adds no new model files: it reuses the Qwen-Image-Edit-2511 stage models above and LTX-2.5.

## Verification log (2026-10-16)

- **Hashes and sizes:** `certutil -hashfile <path> SHA256` on the four LTX files and the Depth ckpt was planned; the hashes were actually computed with `sha256sum` (coreutils, Git Bash) and `stat -c %s` on the files in `<models-dir>` and `<models-dir>`. Nothing was downloaded or deleted.
- **Cross-check:** the HF cache `.metadata` files in the download cache folder and the Depth `.cache` file record the LFS sha256 as their second line. All four LTX hashes and the Depth hash match the computed values.
- **LTX-2.5 license:** `https://huggingface.co/Lightricks/LTX-2.5/raw/main/LICENSE` and `.../README.md` return "Access to model Lightricks/LTX-2.5 is restricted" (gated, no auth in this session), so the raw files could not be read. Instead, `https://huggingface.co/api/models/Lightricks/LTX-2.5` gives `license: other`, `license_name: ltx-2.x-community-license-agreement`, `license_link: https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x`. The license text was taken from that GitHub link (raw.githubusercontent.com/Lightricks/LTX-2/main/LICENSE-2_x, 34,550 bytes, "License date: August 11, 2026").
- **LTX-2.5 revenue threshold (Section 2.1):** "Entities with annual revenues of at least $10,000,000 (the "Commercial Entities") are required to obtain a paid license for any use (excluding use solely for a Non-Commercial Purpose as set forth in Section 2.2) of LTX-2.x and Derivatives of LTX-2.x". Section 2.2 says Commercial Entities may use it without a paid license only for personal or non-production R&D; revenue-generating or end-user-facing use is not Non-Commercial. Derivatives carry the license (Section 1.5).
- **Depth Anything V2 ViT-S license:** raw README at `https://huggingface.co/depth-anything/Depth-Anything-V2-Small/raw/main/README.md` front-matter `license: apache-2.0`. The HF API also reports `license:apache-2.0`.
- **Not verified:**
  - The Gemma-4 12B text encoder's own upstream terms, which may carry separate Gemma terms beyond the LTX license. The row cites the LTX license only.
  - Per-file license terms for the VAE files (none exist separately; the repo-level license is assumed to cover them).
  - The `license:` line in the LTX README front-matter, because the README is gated. The HF API `cardData.license` field was used instead.
  - Whether the local LTX files were downloaded under a gated account that accepted the terms. Their presence in `_ltx25_dl` suggests yes, but nothing confirms the acceptance.
