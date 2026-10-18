"""Download the LTX-2.5 files the official I2V template needs into the models directory
(OPENSAUCE_MODELS_DIR, default ../comfy-opensauce-install/models; put it on fast local storage). Requires the HF account to have accepted the
gate at https://huggingface.co/Lightricks/LTX-2.5 (else every file is 403).

  python scripts/download_ltx25.py  >> <comfy-install>/download.log 2>&1
"""
import os
import sys
import time

from huggingface_hub import hf_hub_download

ROOT = os.environ.get("OPENSAUCE_MODELS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "comfy-opensauce-install", "models"))
FILES = [  # (repo path, models subfolder)  ~ 21.5 + 1.5 + 0.4 + ~13 + 1 GB
    ("latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", "latent_upscale_models"),
    ("vae/ltx-2.5-video-vae-bf16.safetensors", "vae"),
    ("vae/ltx-2.5-audio-vae-bf16.safetensors", "vae"),
    ("text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "text_encoders"),
    ("diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", "diffusion_models"),
]

for path, sub in FILES:
    dst_dir = os.path.join(ROOT, sub)
    os.makedirs(dst_dir, exist_ok=True)
    if os.path.exists(os.path.join(dst_dir, os.path.basename(path))):
        print("exists", path, flush=True)
        continue
    t = time.time()
    print("start", path, flush=True)
    try:
        f = hf_hub_download("Lightricks/LTX-2.5", path, local_dir=os.path.join(ROOT, "_ltx25_dl"))
    except Exception as e:
        sys.exit(f"FAILED {path}: {e}")
    os.replace(f, os.path.join(dst_dir, os.path.basename(path)))
    print(f"done {path} {time.time() - t:.0f}s", flush=True)
print("ALL DONE", flush=True)
