[CmdletBinding()]
param(
    [switch]$PurgeIdentityAndTelemetry
)

$ErrorActionPreference = "Stop"
$uninstallRoots = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)
$product = @(foreach ($root in $uninstallRoots) {
    Get-ChildItem $root -ErrorAction SilentlyContinue |
        Get-ItemProperty -ErrorAction SilentlyContinue |
        Where-Object DisplayName -eq "Nawari Endpoint Agent"
}) | Select-Object -First 1
if ($product) {
    $productCode = Split-Path $product.PSPath -Leaf
    $process = Start-Process msiexec.exe -ArgumentList "/x $productCode /qn /norestart" -Wait -PassThru
    if ($process.ExitCode -notin @(0, 1605, 1641, 3010)) { exit $process.ExitCode }
}

$markerPath = "HKLM:\Software\Nawari\Endpoint Deployment"
$marker = Get-ItemProperty $markerPath -ErrorAction SilentlyContinue
if ($marker.NetdataInstalledByPackage -eq 1) {
    $netdata = @(foreach ($root in $uninstallRoots) {
        Get-ChildItem $root -ErrorAction SilentlyContinue |
            Get-ItemProperty -ErrorAction SilentlyContinue |
            Where-Object DisplayName -Like "Netdata*"
    }) | Select-Object -First 1
    if ($netdata) {
        $netdataProductCode = Split-Path $netdata.PSPath -Leaf
        Start-Process msiexec.exe -ArgumentList "/x $netdataProductCode /qn /norestart" -Wait | Out-Null
    }
}

Remove-Item $markerPath -Recurse -Force -ErrorAction SilentlyContinue
if ($PurgeIdentityAndTelemetry) {
    Remove-Item "$env:ProgramData\Nawari\Endpoint Agent" -Recurse -Force -ErrorAction SilentlyContinue
}
