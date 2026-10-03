# One controlled LTX-2.5 admission/diagnostic run: monitor.py wrapping comfy_run.py (ComfyUI launched as a child).
#
#   powershell -ExecutionPolicy Bypass -File tools\windows\run_admission.ps1 -Label ltx25-m2a-temple `
#       -Workflow workflows\ltx25\m2a_temple_api.json -InputDir G:\onecreations\renders\m2a_temple `
#       -Meta rung=m2a,purpose=representative-scene -Notes "..."
#
# InputDir must contain first_frame.png, depth_control.mp4 and depth_control.json (make_controls.py sidecar); it is
# passed to ComfyUI as --input-directory. Their SHA-256 (and the workflow's) are recorded as monitor meta.
# The fixed generation settings (512x320x49, 8 steps, strengths) live in the workflow and are recorded as meta here.
# -RecordsDir (default admission_records) sends the monitor's records.jsonl and CSV elsewhere, e.g.
# admission_records\showcase for showcase runs that are not admission experiments.
# Kept ASCII-only for Windows PowerShell 5.1. Uses the session-only environment from oc_env.ps1.

param(
    [Parameter(Mandatory = $true)] [string]$Label,
    [Parameter(Mandatory = $true)] [string]$Workflow,
    [Parameter(Mandatory = $true)] [string]$InputDir,
    [int]$Seed = 1000,
    [int]$Repeat = 1,
    [string]$Sysmem = "driver-default",
    [string]$ComfyFlags = "",
    [string[]]$Meta = @(),
    [string]$Notes = "n/a",
    [string]$RecordsDir = "admission_records"
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Repo
. "$Repo\tools\windows\oc_env.ps1" | Out-Null
$Data = $env:ONECREATIONS_DATA
$RunDate = Get-Date -Format "yyyy-MM-dd"
$OutDir = Join-Path $Data "experiments\${RunDate}_$Label"
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower() }
$WorkflowPath = Join-Path $Repo $Workflow
$FirstFrame = Join-Path $InputDir "first_frame.png"
$Control = Join-Path $InputDir "depth_control.mp4"
$Sidecar = Join-Path $InputDir "depth_control.json"
foreach ($f in @($WorkflowPath, $FirstFrame, $Control, $Sidecar)) { if (-not (Test-Path -LiteralPath $f)) { throw "missing input: $f" } }
$BundleSha = (Get-Content -LiteralPath $Sidecar -Raw | ConvertFrom-Json).source_content_sha256

$ComfyArgs = @("$Data\comfy\.venv\Scripts\python.exe", "$Data\comfy\ComfyUI\main.py", "--port", "8188",
               "--disable-auto-launch", "--extra-model-paths-config", "$Data\comfy\extra_model_paths.yaml",
               "--output-directory", $OutDir, "--input-directory", $InputDir, "--temp-directory", "$Data\temp\comfy")
if ($ComfyFlags) { $ComfyArgs += ($ComfyFlags -split ' ') }
$FlagMeta = if ($ComfyFlags) { $ComfyFlags -replace ' ', '_' } else { "none" }
$Seeds = (0..($Repeat - 1) | ForEach-Object { $Seed + $_ }) -join ","

$MetaArgs = @("workflow=$Workflow", "workflow_sha256=$(Get-Sha256 $WorkflowPath)",
              "first_frame_sha256=$(Get-Sha256 $FirstFrame)", "depth_control_sha256=$(Get-Sha256 $Control)",
              "bundle_content_sha256=$BundleSha", "inputs=$InputDir", "seeds=$Seeds", "sysmem=$Sysmem",
              "comfy_flags=$FlagMeta", "output_dir=$OutDir", "comfy_report=$OutDir\report.json")
foreach ($m in $Meta) { $MetaArgs += ($m -split ',') }

$RecordsPath = Join-Path $Repo $RecordsDir
New-Item -ItemType Directory -Force $RecordsPath | Out-Null
& uv run python tools\admission\monitor.py --label $Label --interval 1 --out-dir $RecordsPath `
    --meta @MetaArgs --notes $Notes -- `
    "$Repo\.venv\Scripts\python.exe" tools\admission\comfy_run.py --workflow $Workflow `
    --repeat $Repeat --seed "8/noise_seed=$Seed" --timeout 3600 --ready-timeout 900 `
    --report "$OutDir\report.json" --launch-log "$OutDir\comfy.log" -- @ComfyArgs
"monitor exit: $LASTEXITCODE"
"output dir: $OutDir"
