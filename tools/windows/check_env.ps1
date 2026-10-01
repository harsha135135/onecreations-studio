# OneCreations desktop environment check (gate G0). Read-only: changes nothing.
#
#   powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1
#   powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1 -DataRoot E:\onecreations -TorchPython C:\envs\comfyui\.venv\Scripts\python.exe
#
# Exit code 0 = no FAIL lines (WARN lines still need a human look). Kept ASCII-only for Windows PowerShell 5.1.

param(
    [string]$DataRoot = "D:\onecreations",
    [string]$TorchPython = "",
    [int]$IdleVramWarnMB = 600,
    [int]$MinFreeGB = 500
)

$script:fails = 0
$script:warns = 0
function Pass($msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:warns++ }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; $script:fails++ }
function Info($msg) { Write-Host "[INFO] $msg" }

Write-Host "=== OneCreations environment check (G0) ==="

# --- OS / CPU / RAM ---------------------------------------------------------
$os = Get-CimInstance Win32_OperatingSystem
Info "OS: $($os.Caption) build $($os.BuildNumber)"
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Info "CPU: $($cpu.Name.Trim()) ($($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads)"

$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
if ($ramGB -ge 30) { Pass "RAM: $ramGB GB visible (plan assumes 32 GB; see ADR-0001 D5)" }
else { Fail "RAM: only $ramGB GB visible; plan assumes 32 GB" }
$freeRamGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 1)
Info "RAM free right now: $freeRamGB GB (close browsers/Blender before admission runs)"

# --- Pagefile ---------------------------------------------------------------
if ($cs.AutomaticManagedPagefile) {
    Warn "Pagefile is system-managed. Runbook asks for a fixed-size pagefile on the fastest NVMe (safety net for model loading)."
} else {
    $pf = Get-CimInstance Win32_PageFileSetting
    foreach ($p in $pf) { Info "Pagefile setting: $($p.Name) initial=$($p.InitialSize) MB max=$($p.MaximumSize) MB" }
    if (-not $pf) { Warn "No pagefile configured. Model loading on 32 GB RAM may fail without one." }
    else { Pass "Fixed pagefile configured" }
}
$pfu = Get-CimInstance Win32_PageFileUsage
foreach ($u in $pfu) { Info "Pagefile usage: $($u.Name) allocated=$($u.AllocatedBaseSize) MB current=$($u.CurrentUsage) MB peak=$($u.PeakUsage) MB" }

# --- GPUs / display ---------------------------------------------------------
$vcs = Get-CimInstance Win32_VideoController
foreach ($vc in $vcs) { Info "Video controller: $($vc.Name) (driver $($vc.DriverVersion))" }
if ($vcs | Where-Object { $_.Name -match "Intel" }) { Pass "Intel iGPU is enabled (needed to drive the display)" }
else { Warn "Intel iGPU not visible. Enable it in BIOS and connect the monitor to the motherboard output (ADR-0001 D6)." }

$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) {
    Fail "nvidia-smi not found: install/repair the NVIDIA driver"
} else {
    $q = & nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,display_active,display_mode,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader,nounits
    $f = $q.Split(",") | ForEach-Object { $_.Trim() }
    Info "NVIDIA: $($f[0]) driver $($f[1]), $($f[2]) MB total, PCIe gen $($f[6]) x$($f[7])"
    if ($f[0] -match "4070") { Pass "RTX 4070 detected" } else { Warn "Expected an RTX 4070, found '$($f[0])'" }
    $used = [int]$f[3]
    if ($used -le $IdleVramWarnMB) { Pass "Idle VRAM in use: $used MB" }
    else { Warn "Idle VRAM in use: $used MB (> $IdleVramWarnMB MB). Display or apps are on the 4070; move the monitor to the iGPU and close GPU apps." }
    if ($f[4] -eq "Disabled") { Pass "No display active on the 4070 (display_active=Disabled)" }
    else { Warn "A display is active on the 4070 (display_active=$($f[4])). Use the iGPU for the desktop." }
    if (($f[7] -match '^\d+$') -and ([int]$f[7] -lt 16)) { Warn "PCIe link width x$($f[7]) at idle (may downclock when idle; re-check under load). Offload speed depends on x16." }
}

Info "MANUAL CHECK: NVIDIA Control Panel > Manage 3D settings > Program settings > each venv python.exe > 'CUDA - Sysmem Fallback Policy' = 'Prefer No Sysmem Fallback'."

# --- Storage ----------------------------------------------------------------
$drive = Split-Path -Qualifier $DataRoot
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$drive'"
if (-not $disk) {
    Fail "Data root drive $drive not found (DataRoot=$DataRoot). Pass -DataRoot to point at your NVMe data drive."
} else {
    $freeGB = [math]::Round($disk.FreeSpace / 1GB)
    $sizeGB = [math]::Round($disk.Size / 1GB)
    if ($freeGB -ge $MinFreeGB) { Pass "Data drive ${drive}: $freeGB GB free of $sizeGB GB" }
    else { Warn "Data drive ${drive}: only $freeGB GB free of $sizeGB GB (plan wants >= $MinFreeGB GB for models + caches)" }
    if (Test-Path $DataRoot) { Pass "Data root exists: $DataRoot" } else { Warn "Data root $DataRoot does not exist yet (create models\, datasets\, caches\, renders\)" }
    if ($DataRoot -match "OneDrive") { Fail "Data root is inside OneDrive; move it out (sync will thrash on multi-GB files)" }
}

# --- Tools ------------------------------------------------------------------
foreach ($tool in @("git", "uv")) {
    $c = Get-Command $tool -ErrorAction SilentlyContinue
    if ($c) { Pass "$tool found: $($c.Source)" } else { Fail "$tool not found on PATH" }
}
$blender = Get-Command blender -ErrorAction SilentlyContinue
if ($blender) {
    $bv = (& blender --version 2>$null | Select-Object -First 1)
    if ($bv -match "4\.5") { Pass "Blender: $bv" } else { Warn "Blender on PATH is '$bv'; plan pins Blender 4.5 LTS" }
} else { Warn "blender not on PATH (fine if installed elsewhere; scripts will need its path)" }

# --- WSL (informational) ----------------------------------------------------
$wslcfg = Join-Path $env:USERPROFILE ".wslconfig"
if (Test-Path $wslcfg) { Info ".wslconfig present (GPU training runs natively on Windows, not WSL, per ADR-0001 D6)" }

# --- Optional torch check in a given venv -----------------------------------
if ($TorchPython -ne "") {
    if (Test-Path $TorchPython) {
        $code = "import torch;print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-', torch.cuda.is_bf16_supported() if torch.cuda.is_available() else '-')"
        $out = & $TorchPython -c $code 2>&1
        if ($LASTEXITCODE -eq 0 -and $out -match "True") { Pass "torch in ${TorchPython}: $out" }
        else { Fail "torch check failed in ${TorchPython}: $out" }
    } else { Fail "TorchPython not found: $TorchPython" }
}

Write-Host ""
Write-Host "=== Result: $script:fails FAIL, $script:warns WARN ==="
if ($script:fails -gt 0) { exit 1 } else { exit 0 }
