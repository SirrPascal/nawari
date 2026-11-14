[CmdletBinding()]
param([switch]$RemoveNetdataWhenPackageOwned)

$ErrorActionPreference = "Stop"
$root = "$env:ProgramFiles\Netdata"
$collector = Join-Path $root "usr\libexec\netdata\plugins.d\nawari.plugin.exe"
$config = Join-Path $root "etc\netdata\nawari-collector.json"
$markerPath = "HKLM:\Software\Nawari\Netdata Extension"
$marker = Get-ItemProperty $markerPath -ErrorAction SilentlyContinue

Stop-Service Netdata -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $collector -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue

if ($RemoveNetdataWhenPackageOwned -and $marker.NetdataInstalledByPackage -eq 1) {
    $uninstall = Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        Get-ItemProperty -ErrorAction SilentlyContinue |
        Where-Object DisplayName -Like "Netdata*" |
        Select-Object -First 1
    if ($uninstall) {
        $productCode = Split-Path $uninstall.PSPath -Leaf
        Start-Process msiexec.exe -ArgumentList "/qn /x $productCode" -Wait | Out-Null
    }
} else {
    Start-Service Netdata -ErrorAction SilentlyContinue
}
Remove-Item $markerPath -Recurse -Force -ErrorAction SilentlyContinue
