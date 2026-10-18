#!/usr/bin/env bash
# OPEN SAUCE installer (Linux/macOS/Git Bash). Mirrors scripts/install.ps1.
#   scripts/install.sh --models-dir /data/opensauce-models [--root DIR] [--python python3] [--dry-run]
# Pins mirror docs/stack.md. Needs git and Python 3.12+. LTX-2.5 is gated and is NEVER downloaded here.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$REPO/../comfy-opensauce-install"
MODELS_DIR=""
PYTHON="python3"
TORCH_INDEX="https://download.pytorch.org/whl/cu130"   # dev box ran torch 2.10.0+cu130; pick the index for your CUDA
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --models-dir) MODELS_DIR="$2"; shift 2 ;;
    --root) ROOT="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    --torch-index) TORCH_INDEX="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[ -n "$MODELS_DIR" ] || { echo "--models-dir is required" >&2; exit 2; }

COMFY_URL="https://github.com/Comfy-Org/ComfyUI"
COMFY_COMMIT="b53f77a74e21091cbdebfdf7b85fc80326932646"   # tag v0.41.2
PACKS=(
  "ComfyUI-LTXVideo|https://github.com/Lightricks/ComfyUI-LTXVideo|44c8a36b7c31ee00b4271daed11dc2a4aa481140"
  "comfyui_controlnet_aux|https://github.com/Fannovel16/comfyui_controlnet_aux|a587a4c1594524c1d2de5cd1a86cd868ff448e1c"
  "ComfyUI-VideoHelperSuite|https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite|4d907bee61e92c2e65af3bd6383a4e4d356126d1"
  "ComfyUI-GGUF|https://github.com/city96/ComfyUI-GGUF|6ea2651e7df66d7585f6ffee804b20e92fb38b8a"
  "ComfyUI_BiRefNet_ll|https://github.com/lldacing/ComfyUI_BiRefNet_ll|5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529"
)
APP_DEPS=(comfy-sdk comfy-api-proxy opencv-python numpy pillow qrcode mutagen imageio-ffmpeg)

step() { printf '==> %s\n' "$*"; }
run() { printf '    %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }
in_dir() { local d="$1"; shift; printf '    (cd %s) %s\n' "$d" "$*"; [ "$DRY" = 1 ] || ( cd "$d" && "$@" ); }
gitpin() { # url dest ref
  if [ -d "$2/.git" ]; then echo "    exists, skipping: $2"; return; fi
  run git init -q "$2"
  in_dir "$2" git remote add origin "$1"
  in_dir "$2" git fetch --depth 1 origin "$3"
  in_dir "$2" git checkout -q FETCH_HEAD
}

echo "OPEN SAUCE install   repo=$REPO"
echo "                     comfy=$ROOT  models=$MODELS_DIR  dryrun=$DRY"

step "ComfyUI v0.41.2 ($COMFY_COMMIT)"
gitpin "$COMFY_URL" "$ROOT" "$COMFY_COMMIT"

step "venv + Python dependencies"
VPY="$ROOT/.venv/bin/python"
[ -x "$VPY" ] || run "$PYTHON" -m venv "$ROOT/.venv"
run "$VPY" -m pip install --upgrade pip
run "$VPY" -m pip install torch torchvision torchaudio --index-url "$TORCH_INDEX"
run "$VPY" -m pip install -r "$ROOT/requirements.txt"
run "$VPY" -m pip install "${APP_DEPS[@]}"

step "custom node packs (pinned commits)"
for entry in "${PACKS[@]}"; do
  IFS='|' read -r name url commit <<<"$entry"
  gitpin "$url" "$ROOT/custom_nodes/$name" "$commit"
  # Non-fatal: some packs pin opencv/numpy versions that try to build from source on very new Pythons.
  if [ "$DRY" = 1 ] || [ -f "$ROOT/custom_nodes/$name/requirements.txt" ]; then
    run "$VPY" -m pip install -r "$ROOT/custom_nodes/$name/requirements.txt" || echo "    WARNING: requirements for $name failed (continuing)"
  fi
done

step "ShotGrammar (symlink to this repo)"
if [ -e "$ROOT/custom_nodes/shotgrammar" ]; then echo "    exists, skipping"; else run ln -s "$REPO/custom_nodes/shotgrammar" "$ROOT/custom_nodes/shotgrammar"; fi

step "extra_model_paths.yaml -> $MODELS_DIR"
YAML="opensauce_models:
    base_path: $MODELS_DIR
    is_default: true
    diffusion_models: diffusion_models
    text_encoders: text_encoders
    vae: vae
    loras: loras
    latent_upscale_models: latent_upscale_models
    birefnet: BiRefNet"
echo "$YAML"
if [ "$DRY" != 1 ]; then
  mkdir -p "$MODELS_DIR"/{diffusion_models,text_encoders,vae,loras,latent_upscale_models,BiRefNet}
  printf '%s\n' "$YAML" > "$ROOT/extra_model_paths.yaml"
fi

step "models to download into $MODELS_DIR (details, licenses and sha256: MODELS.md)"
HF="https://huggingface.co"
cat <<EOF
GATED  LTX-2.5 (LTX-2.x Community License, free under USD 10M revenue). NOT downloaded by this script.
       1. Sign in at $HF/Lightricks/LTX-2.5 and click "Agree and access repository".
       2. Create a read token at $HF/settings/tokens, then run:  hf auth login
       3. Run:  $VPY scripts/download_ltx25.py   with OPENSAUCE_MODELS_DIR=$MODELS_DIR
       Files: diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors
              text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors
              vae/ltx-2.5-video-vae-bf16.safetensors, vae/ltx-2.5-audio-vae-bf16.safetensors
              latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors

OPEN   Petrify stage (Apache-2.0 / MIT), only needed for the Petrify preset:
       diffusion_models/qwen-image-edit-2511-Q4_K_M.gguf
           $HF/unsloth/Qwen-Image-Edit-2511-GGUF/blob/1daa38515d/qwen-image-edit-2511-Q4_K_M.gguf
       text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
           $HF/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
       vae/qwen_image_vae.safetensors
           $HF/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/vae/qwen_image_vae.safetensors
       BiRefNet/General.safetensors   (download model.safetensors and rename)
           $HF/ZhengPeng7/BiRefNet/resolve/e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4/model.safetensors

AUTO   Depth Anything V2 ViT-S (Apache-2.0): comfyui_controlnet_aux downloads depth_anything_v2_vits.pth on first use
       ($HF/depth-anything/Depth-Anything-V2-Small).
EOF

step "next"
cat <<EOF
  1. start ComfyUI : cd $ROOT && .venv/bin/python main.py --listen 127.0.0.1 --port 8189
  2. start proxy   : comfy-api-proxy start --comfyui http://127.0.0.1:8189 --port 8190 --comfyui-base-dir $ROOT
  3. render        : python -m app render levitate --image you.jpg
EOF
[ "$DRY" = 1 ] && echo "(dry run: nothing was changed)"
exit 0
