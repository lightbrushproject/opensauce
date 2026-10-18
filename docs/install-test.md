# Install test: README-only install on a second machine

Date: 2026-10-17. Repo HEAD at test time: `git archive HEAD` of branch feat/taoceramic-render-v7-upgrade (stand-in for a stranger's clone).

## Machine
- Second machine: Windows laptop, RTX 5090 Laptop 24 GB (about 20 GB VRAM in use by another process; untouched, no GPU render run), 64 GB RAM, Python 3.14.0 (C:\Python314), git 2.52.0, Windows PowerShell 5.1.
- Drive: C: (35.9 GB free before; D: has 0 GB). Everything under `C:\opensauce-test\`. Coordinator relaxed the 40 GB rule because no models are downloaded. Abort guard was 8 GB free; the lowest seen was about 30.3 GB.

## What was run
```
git archive -o opensauce.zip HEAD ; scp ; Expand-Archive -> C:\opensauce-test\open-sauce
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -ModelsDir C:\opensauce-test\models     # exactly the README line, not -DryRun
```
Log: 736 lines, kept outside the repo.

## Timings
| Step | Time |
|---|---|
| Whole `install.ps1` (ComfyUI fetch, venv, torch 2.14.1+cu130, requirements, 5 node packs, junction, yaml) | 5 min 34 s, exit 0 |
| ComfyUI start to `/system_stats` answering | under 1 min (polled every 8 s) |
| `/object_info` fetch + class check | seconds |

## What failed and the fix
Nothing failed. `scripts/install.ps1` was NOT modified. Observations:
- Installed `torch 2.14.1+cu130`, not the 2.10.0+cu130 the dev box ran (the script does not pin torch). ComfyUI v0.41.2 started fine with it. Pinning is optional follow-up.
- Under Windows PowerShell 5.1, git's stderr progress ("From https://...") is shown as a NativeCommandError block in the log. That is only because the log was captured with `*>` redirection. It is cosmetic, and the script continued and exited 0.
- Redirected output is UTF-16; the copy in tmp/ was converted to UTF-8.
- Test-harness note: `Start-Process` from an ssh session died with the session; processes were started detached via `Invoke-CimMethod Win32_Process Create`.

## Verification
- ComfyUI 0.41.2 (frontend 1.55.17, templates 0.11.86) started on 127.0.0.1:8189; `shotgrammar` custom node loaded (0.1 s); no IMPORT FAILED lines.
- `/object_info` returned 1167 classes. The 55 distinct `class_type`s used across `workflows/*.api.json` (8 files) are all present: 0 missing. Model-file existence was not checked (no models downloaded).
- Stopped only PID 25252 (cmdline contained `main.py ... --port 8189`); port 8189 no longer listening. No other process touched.

## Remaining steps (on any new machine)
1. Accept the LTX gate for this HF account: https://huggingface.co/Lightricks/LTX-2.5 -> "Agree and access repository"; create a read token; `hf auth login`.
2. Download models (about 37 GB; needs a drive with that space free, C: has about 30 GB, so use a bigger drive or free space first):
   ```
   $env:OPENSAUCE_MODELS_DIR = "C:\opensauce-test\models"
   C:\opensauce-test\comfy-opensauce-install\.venv\Scripts\python.exe C:\opensauce-test\open-sauce\scripts\download_ltx25.py
   ```
   Petrify-stage files (Qwen GGUF, text encoder, VAE, BiRefNet General.safetensors) per the list printed by install.ps1 / MODELS.md.
3. Start ComfyUI and the proxy, then one render (needs about 24 GB free VRAM, so stop or finish whatever else holds the GPU first):
   ```
   cd C:\opensauce-test\comfy-opensauce-install
   .\.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8189 --disable-auto-launch
   cd C:\opensauce-test\open-sauce
   powershell -File scripts\start_proxy.ps1 -ComfyDir C:\opensauce-test\comfy-opensauce-install
   python -m app render levitate --image you.jpg
   ```
   (the app needs `comfy-sdk` etc., which are in the venv; use the venv python for `-m app`).
