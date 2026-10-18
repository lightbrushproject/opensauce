# Launch the OpenSauce clean ComfyUI install on port 8189 (detached, hidden).
# Never kills anything. Production ComfyUI (8188) is untouched.
param(
    [string]$Root = $(if ($env:COMFY_DIR) { $env:COMFY_DIR } else { Join-Path (Split-Path $PSScriptRoot -Parent) "..\comfy-opensauce-install" }),
    [int]$Port = 8189,
    [string]$ExtraArgs = ""
)
$py  = Join-Path $Root ".venv\Scripts\python.exe"
$log = Join-Path $Root "opensauce.log"
$err = Join-Path $Root "opensauce.err.log"

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Port $Port already in use by PID $($busy.OwningProcess). Not starting."; exit 1 }

$argList = "main.py --listen 127.0.0.1 --port $Port --disable-auto-launch $ExtraArgs".Trim()
$p = Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $Root `
     -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
Set-Content -Path (Join-Path $Root "opensauce.pid") -Value $p.Id
Write-Host "Started ComfyUI PID $($p.Id) on http://127.0.0.1:$Port  (logs: $log, $err)"
Write-Host "PID $($p.Id) is the venv launcher; the server is its child. Stop only the server with:"
Write-Host "  Stop-Process -Id (Get-NetTCPConnection -LocalPort $Port -State Listen).OwningProcess"
