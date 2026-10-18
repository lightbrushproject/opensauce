<#
OPEN SAUCE installer (Windows). Builds a clean, pinned ComfyUI next to this repo.

  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -ModelsDir D:\opensauce-models
  powershell -File scripts\install.ps1 -ModelsDir D:\opensauce-models -DryRun     # print the plan, change nothing

What it does:
  1. clones ComfyUI at the pinned tag into -Root (default <repo>\..\comfy-opensauce-install)
  2. creates a venv, installs torch + ComfyUI requirements + the app's Python deps
  3. clones the pinned custom node packs at their exact commits
  4. links this repo's custom_nodes\shotgrammar into ComfyUI (junction)
  5. writes extra_model_paths.yaml pointing at -ModelsDir
  6. prints the model download list (LTX-2.5 is gated and is NEVER downloaded automatically)
Pins mirror docs/stack.md. Needs: git, Python 3.12+ on PATH (3.14 was used on the dev box), ~80 GB free for models.
#>
param(
    [Parameter(Mandatory = $true)][string]$ModelsDir,
    [string]$Root = "",
    [string]$Python = "python",
    [string]$TorchIndex = "https://download.pytorch.org/whl/cu130",   # dev box ran torch 2.10.0+cu130; pick the index for your CUDA
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Repo = Split-Path $ScriptDir -Parent
if (-not $Root) { $Root = Join-Path $Repo "..\comfy-opensauce-install" }
$Root = [IO.Path]::GetFullPath($Root)
$ModelsDir = [IO.Path]::GetFullPath($ModelsDir)

$ComfyUrl = "https://github.com/Comfy-Org/ComfyUI"
$ComfyTag = "v0.41.2"
$ComfyCommit = "b53f77a74e21091cbdebfdf7b85fc80326932646"
$Packs = @(
    @{ Name = "ComfyUI-LTXVideo";           Url = "https://github.com/Lightricks/ComfyUI-LTXVideo";           Commit = "44c8a36b7c31ee00b4271daed11dc2a4aa481140" },
    @{ Name = "comfyui_controlnet_aux";     Url = "https://github.com/Fannovel16/comfyui_controlnet_aux";     Commit = "a587a4c1594524c1d2de5cd1a86cd868ff448e1c" },
    @{ Name = "ComfyUI-VideoHelperSuite";   Url = "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite";  Commit = "4d907bee61e92c2e65af3bd6383a4e4d356126d1" },
    @{ Name = "ComfyUI-GGUF";               Url = "https://github.com/city96/ComfyUI-GGUF";                   Commit = "6ea2651e7df66d7585f6ffee804b20e92fb38b8a" },
    @{ Name = "ComfyUI_BiRefNet_ll";        Url = "https://github.com/lldacing/ComfyUI_BiRefNet_ll";          Commit = "5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529" }
)
$AppDeps = @("comfy-sdk", "comfy-api-proxy", "opencv-python", "numpy", "pillow", "qrcode", "mutagen", "imageio-ffmpeg")

function Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Run([string]$exe, [string[]]$a, [string]$cwd = $null) {
    Write-Host ("    " + $exe + " " + ($a -join " "))
    if ($DryRun) { return }
    if ($cwd) { Push-Location $cwd }
    try { & $exe @a; if ($LASTEXITCODE -ne 0) { throw "$exe exited $LASTEXITCODE" } } finally { if ($cwd) { Pop-Location } }
}
function GitPin([string]$url, [string]$dest, [string]$ref) {
    if (Test-Path (Join-Path $dest ".git")) { Write-Host "    exists, skipping: $dest"; return }
    Run git @("init", "-q", $dest)
    Run git @("remote", "add", "origin", $url) $dest
    Run git @("fetch", "--depth", "1", "origin", $ref) $dest
    Run git @("checkout", "-q", "FETCH_HEAD") $dest
}

Write-Host "OPEN SAUCE install   repo=$Repo"
Write-Host "                     comfy=$Root  models=$ModelsDir  dryrun=$($DryRun.IsPresent)"

Step "ComfyUI $ComfyTag ($ComfyCommit)"
GitPin $ComfyUrl $Root $ComfyCommit

Step "venv + Python dependencies"
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { Run $Python @("-m", "venv", (Join-Path $Root ".venv")) }
Run $venvPy @("-m", "pip", "install", "--upgrade", "pip")
Run $venvPy @("-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", $TorchIndex)
Run $venvPy @("-m", "pip", "install", "-r", (Join-Path $Root "requirements.txt"))
Run $venvPy (@("-m", "pip", "install") + $AppDeps)

Step "custom node packs (pinned commits)"
$cn = Join-Path $Root "custom_nodes"
foreach ($p in $Packs) {
    GitPin $p.Url (Join-Path $cn $p.Name) $p.Commit
    $req = Join-Path $cn "$($p.Name)\requirements.txt"
    if ($DryRun -or (Test-Path $req)) {
        # Non-fatal: some packs pin opencv/numpy versions that try to build from source on very new Pythons.
        try { Run $venvPy @("-m", "pip", "install", "-r", $req) } catch { Write-Warning "requirements for $($p.Name) failed: $_ (continuing; most deps are already installed)" }
    }
}

Step "ShotGrammar (junction to this repo)"
$link = Join-Path $cn "shotgrammar"
$target = Join-Path $Repo "custom_nodes\shotgrammar"
if (Test-Path $link) { Write-Host "    exists, skipping: $link" }
else {
    Write-Host "    junction $link -> $target"
    if (-not $DryRun) { New-Item -ItemType Junction -Path $link -Target $target | Out-Null }
}

Step "extra_model_paths.yaml -> $ModelsDir"
$yaml = @"
opensauce_models:
    base_path: $($ModelsDir -replace '\\', '/')
    is_default: true
    diffusion_models: diffusion_models
    text_encoders: text_encoders
    vae: vae
    loras: loras
    latent_upscale_models: latent_upscale_models
    birefnet: BiRefNet
"@
Write-Host $yaml
if (-not $DryRun) {
    New-Item -ItemType Directory -Force $ModelsDir | Out-Null
    foreach ($d in "diffusion_models", "text_encoders", "vae", "loras", "latent_upscale_models", "BiRefNet") { New-Item -ItemType Directory -Force (Join-Path $ModelsDir $d) | Out-Null }
    Set-Content -Path (Join-Path $Root "extra_model_paths.yaml") -Value $yaml -Encoding UTF8
}

Step "models to download into $ModelsDir (details, licenses and sha256: MODELS.md)"
$base = "https://huggingface.co"
@"
GATED  LTX-2.5 (LTX-2.x Community License, free under USD 10M revenue). NOT downloaded by this script.
       1. Sign in at $base/Lightricks/LTX-2.5 and click "Agree and access repository".
       2. Create a read token at $base/settings/tokens, then run:  hf auth login
       3. Run:  $venvPy scripts\download_ltx25.py   with OPENSAUCE_MODELS_DIR set to $ModelsDir
       Files: diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors
              text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors
              vae/ltx-2.5-video-vae-bf16.safetensors, vae/ltx-2.5-audio-vae-bf16.safetensors
              latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors

OPEN    Petrify stage (Apache-2.0 / MIT), only needed for the Petrify preset:
       diffusion_models/qwen-image-edit-2511-Q4_K_M.gguf
           $base/unsloth/Qwen-Image-Edit-2511-GGUF/blob/1daa38515d/qwen-image-edit-2511-Q4_K_M.gguf
       text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
           $base/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
       vae/qwen_image_vae.safetensors
           $base/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/vae/qwen_image_vae.safetensors
       BiRefNet/General.safetensors   (download model.safetensors and rename)
           $base/ZhengPeng7/BiRefNet/resolve/e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4/model.safetensors

AUTO    Depth Anything V2 ViT-S (Apache-2.0): comfyui_controlnet_aux downloads depth_anything_v2_vits.pth on first use
       ($base/depth-anything/Depth-Anything-V2-Small).
"@ | Write-Host

Step "next"
@"
  1. start ComfyUI : cd $Root ; .\.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8189
  2. start proxy   : powershell -File scripts\start_proxy.ps1 -ComfyDir $Root
  3. render        : python -m app render levitate --image you.jpg
"@ | Write-Host
if ($DryRun) { Write-Host "(dry run: nothing was changed)" -ForegroundColor Yellow }
