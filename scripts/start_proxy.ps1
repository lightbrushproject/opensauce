# Start comfy-api-proxy so the official Comfy SDK can drive our local ComfyUI.
#   ComfyUI (clean OpenSauce install) : http://127.0.0.1:8189
#   Proxy (Comfy API v2 surface)      : http://127.0.0.1:8190
# Then: $env:COMFY_BASE_URL="http://127.0.0.1:8190"; $env:COMFY_API_KEY="local"; python scripts/sdk_run.py ...
param(
    [string]$ComfyUrl = "http://127.0.0.1:8189",
    [int]$Port = 8190,
    [string]$ComfyDir = $(if ($env:COMFY_DIR) { $env:COMFY_DIR } else { Join-Path (Split-Path $PSScriptRoot -Parent) "..\comfy-opensauce-install" }),
    [switch]$Foreground
)
$proxy = Join-Path ([Environment]::GetFolderPath("ApplicationData")) "Python\Python314\Scripts\comfy-api-proxy.exe"
if (-not (Test-Path $proxy)) { $proxy = "comfy-api-proxy" }
$stateDir = Join-Path $PSScriptRoot "..\tmp\proxy-state"
New-Item -ItemType Directory -Force $stateDir | Out-Null
$args = @("--comfyui", $ComfyUrl, "--port", $Port, "--comfyui-base-dir", $ComfyDir, "--max-upload-mb", "512", "--state-dir", $stateDir)
if ($Foreground) { & $proxy run @args } else { & $proxy start @args; & $proxy status }
