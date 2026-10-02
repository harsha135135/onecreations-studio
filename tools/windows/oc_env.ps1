# OneCreations data/cache environment for THIS PowerShell session only (no global or registry changes).
#
#   . .\tools\windows\oc_env.ps1                       # dot-source; default data root G:\onecreations
#   . .\tools\windows\oc_env.ps1 -DataRoot X:\OneCreationsData
#
# Keeps every large download and cache on the data drive (nothing big lands on C:). Moving to a new drive means
# copying the data root and passing a different -DataRoot (and updating comfy\extra_model_paths.yaml).
# Kept ASCII-only for Windows PowerShell 5.1.

param([string]$DataRoot = $(if ($env:ONECREATIONS_DATA) { $env:ONECREATIONS_DATA } else { "G:\onecreations" }))

if (-not (Test-Path $DataRoot)) { throw "Data root $DataRoot not found" }
$D = (Resolve-Path $DataRoot).Path

$env:ONECREATIONS_DATA = $D
$env:HF_HOME = Join-Path $D "hf-cache"                 # Hugging Face hub cache, token, xet cache
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$env:TORCH_HOME = Join-Path $D "hf-cache\torch"        # torch.hub / preprocessor checkpoints
$env:UV_CACHE_DIR = Join-Path $D "temp\uv-cache"       # torch/CUDA wheels; same drive as the venvs (hardlinks)
$env:PIP_CACHE_DIR = Join-Path $D "temp\pip-cache"
$env:TEMP = Join-Path $D "temp\tmp"
$env:TMP = $env:TEMP

foreach ($p in @($env:HF_HOME, $env:TORCH_HOME, $env:UV_CACHE_DIR, $env:PIP_CACHE_DIR, $env:TEMP)) {
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

Write-Host "[oc_env] session-only environment (data root $D):"
foreach ($name in @("ONECREATIONS_DATA", "HF_HOME", "TORCH_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "TEMP")) {
    Write-Host ("  {0,-18} {1}" -f $name, (Get-Item "env:$name").Value)
}
