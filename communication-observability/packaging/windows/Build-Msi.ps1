[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "1.0.0",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",
    [string]$SigningThumbprint = $env:NAWARI_SIGNING_THUMBPRINT
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$build = Join-Path $PSScriptRoot "build"
$dist = Join-Path $build "dist"
$msi = Join-Path $build "NawariEndpointAgent-x64.msi"

if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 is required." }
if ($env:PROCESSOR_ARCHITECTURE -notin @("AMD64", "IA64")) { throw "Build from a native x64 shell." }

New-Item -ItemType Directory -Force -Path $build | Out-Null
python -m pip install --requirement (Join-Path $PSScriptRoot "requirements-build.txt")
python -m PyInstaller --noconfirm --clean --distpath $dist --workpath (Join-Path $build "work") (Join-Path $PSScriptRoot "nawari-agent.spec")

$agent = Join-Path $dist "nawari-agent.exe"
if (-not (Test-Path $agent)) { throw "Frozen agent executable was not produced." }
& $agent version
if ($LASTEXITCODE -ne 0) { throw "Frozen agent self-test failed." }

if (-not (Get-Command wix.exe -ErrorAction SilentlyContinue)) {
    throw "WiX Toolset v4 (wix.exe) is required on the Windows build runner."
}

if ($Configuration -eq "Release") {
    if ([string]::IsNullOrWhiteSpace($SigningThumbprint)) {
        throw "Release builds require NAWARI_SIGNING_THUMBPRINT."
    }
    if (-not (Get-Command signtool.exe -ErrorAction SilentlyContinue)) {
        throw "signtool.exe from the Windows SDK is required for Release builds."
    }
    # Sign first so WiX embeds the signed executable in the MSI cabinet.
    signtool.exe sign /sha1 $SigningThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $agent
    signtool.exe verify /pa /all $agent
}

wix build (Join-Path $PSScriptRoot "Product.wxs") `
    -arch x64 `
    -d "ProductVersion=$Version" `
    -d "PayloadDir=$dist" `
    -o $msi
if ($LASTEXITCODE -ne 0) { throw "WiX MSI build failed." }

if ($Configuration -eq "Release") {
    signtool.exe sign /sha1 $SigningThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $msi
    signtool.exe verify /pa /all $msi
}

Get-FileHash -Algorithm SHA256 $agent, $msi
Write-Host "MSI produced at $msi"
