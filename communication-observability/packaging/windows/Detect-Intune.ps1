$ErrorActionPreference = "SilentlyContinue"
$agent = Get-Service "NawariEndpointAgent"
$netdata = Get-Service "Netdata"
$marker = Get-ItemProperty "HKLM:\Software\Nawari\Endpoint Deployment"
$exe = Join-Path $env:ProgramFiles "Nawari\Endpoint Agent\nawari-agent.exe"

if ($agent.Status -eq "Running" -and
    $netdata.Status -eq "Running" -and
    $marker.ManagedPackage -eq 1 -and
    (Test-Path -LiteralPath $exe)) {
    Write-Output "Nawari endpoint deployment detected"
    exit 0
}
exit 1
