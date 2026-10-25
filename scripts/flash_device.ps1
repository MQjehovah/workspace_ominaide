param(
    [string]$Port = "COM3",
    [switch]$Clean,
    [switch]$SyncLibs,
    [switch]$AppOnly,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$started = Get-Date

$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "device"
$Acl = Join-Path $env:LOCALAPPDATA "Programs\arduino-cli\arduino-cli.exe"
$BuildRoot = Join-Path $env:LOCALAPPDATA "Temp\airmouse_build"
$Sketch = Join-Path $BuildRoot "smart_assistant"
$BuildPath = Join-Path $BuildRoot ".build\smart_assistant"
$Sketchbook = Join-Path $env:USERPROFILE "Documents\Arduino\libraries"

if (!(Test-Path $Acl)) { throw "arduino-cli not found: $Acl" }
if (!(Test-Path $Src)) { throw "device directory not found: $Src" }

# Sync the local library patches (small; only when changed).
$srcConf = Join-Path $Src "libraries\lv_conf.h"
$dstConf = Join-Path $Sketchbook "lv_conf.h"
if (!(Test-Path $dstConf) -or ((Get-FileHash $srcConf).Hash -ne (Get-FileHash $dstConf).Hash)) {
    Copy-Item -Force $srcConf $dstConf
}
robocopy (Join-Path $Src "libraries\ESP_SR") (Join-Path $Sketchbook "ESP_SR") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $Src "libraries\omniaide_fonts") (Join-Path $Sketchbook "omniaide_fonts") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($SyncLibs -and (Test-Path (Join-Path $Src "libraries\lvgl"))) {
    robocopy (Join-Path $Src "libraries\lvgl") (Join-Path $Sketchbook "lvgl") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
}

# Mirror the sketch source but skip device/libraries (it lives in sketchbook).
# This is much faster than copying ~800 LVGL files every build.
New-Item -ItemType Directory -Force -Path $Sketch | Out-Null
robocopy $Src $Sketch /MIR /XD (Join-Path $Src "libraries") /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

if ($Clean) {
    Remove-Item -Recurse -Force $BuildPath -ErrorAction SilentlyContinue
}

$Fqbn = "esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=esp_sr_16,PSRAM=opi,FlashMode=qio,USBMode=hwcdc,CDCOnBoot=cdc,UploadSpeed=921600"
$Props = @(
    "--build-property", "upload.maximum_size=4194304",
    "--build-property", "compiler.c.extra_flags=-DCONFIG_SR_MN_EN_NONE",
    "--build-property", "compiler.cpp.extra_flags=-DCONFIG_SR_MN_EN_NONE"
)

Write-Host "[1/2] compile (incremental) ..."
& $Acl compile --fqbn $Fqbn @Props --build-path $BuildPath $Sketch
if ($LASTEXITCODE -ne 0) { throw "compile failed" }

if (!$Full) {
    # Default fast path: write only the app partition at 0x10000.
    # Use -Full after changing partitions.csv / srmodels.bin.
    $Esptool = Get-ChildItem -Recurse -File (Join-Path $env:LOCALAPPDATA "Arduino15\packages\esp32\tools\esptool_py") -Filter "esptool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (!$Esptool) { throw "esptool.exe not found under Arduino15" }
    Write-Host "[2/2] app-only flash $Port ..."
    & $Esptool.FullName --chip esp32s3 --port $Port --baud 921600 `
        --before default_reset --after hard_reset `
        write_flash --flash_mode qio --flash_freq 80m --flash_size 16MB `
        0x10000 (Join-Path $BuildPath "smart_assistant.ino.bin")
    if ($LASTEXITCODE -ne 0) { throw "app-only flash failed" }
} else {
    Write-Host "[2/2] full upload $Port ..."
    & $Acl upload -p $Port --fqbn $Fqbn --input-dir $BuildPath $Sketch
    if ($LASTEXITCODE -ne 0) { throw "upload failed" }
}

$secs = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
Write-Host "done in ${secs}s"
