$ErrorActionPreference = "SilentlyContinue"
$service = Get-Service Netdata
$marker = Get-ItemProperty "HKLM:\Software\Nawari\Netdata Extension"
$collector = Join-Path $env:ProgramFiles "Netdata\usr\libexec\netdata\plugins.d\nawari.plugin.exe"
$charts = Invoke-RestMethod -Uri "http://127.0.0.1:19999/api/v1/charts" -TimeoutSec 3
$hasCharts = [bool]($charts.charts.PSObject.Properties.Name -like "nawari.*")
if ($service.Status -eq "Running" -and $marker.Installed -eq 1 -and
    (Test-Path -LiteralPath $collector) -and $hasCharts) {
    Write-Output "Nawari Netdata endpoint extension detected"
    exit 0
}
exit 1
