[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$NetdataMsi,
    [Parameter(Mandatory)] [string]$NetdataMsiSha256,
    [Parameter(Mandatory)] [string]$CollectorSha256,
    [Parameter(Mandatory)] [string]$CollectorConfig,
    [Parameter(Mandatory)] [string]$StreamConfig,
    [string]$NetdataRoot = "$env:ProgramFiles\Netdata"
)

$ErrorActionPreference = "Stop"
$collectorSource = Join-Path $PSScriptRoot "nawari.plugin.exe"
$pluginDirectory = Join-Path $NetdataRoot "usr\libexec\netdata\plugins.d"
$configDirectory = Join-Path $NetdataRoot "etc\netdata"
$collectorTarget = Join-Path $pluginDirectory "nawari.plugin.exe"
$collectorConfigTarget = Join-Path $configDirectory "nawari-collector.json"
$streamConfigTarget = Join-Path $configDirectory "stream.conf"
$backupDirectory = Join-Path $env:ProgramData "Nawari\Netdata Extension\rollback"

function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Required artifact is absent: $Path" }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw "SHA-256 mismatch: $Path"
    }
}

Assert-Hash $NetdataMsi $NetdataMsiSha256
Assert-Hash $collectorSource $CollectorSha256
if ((Get-AuthenticodeSignature -LiteralPath $NetdataMsi).Status -ne "Valid") {
    throw "The vendor Netdata MSI does not have a valid Authenticode signature."
}
if ((Get-AuthenticodeSignature -LiteralPath $collectorSource).Status -ne "Valid") {
    throw "The Nawari collector does not have a valid Authenticode signature."
}

$netdataWasPresent = [bool](Get-Service Netdata -ErrorAction SilentlyContinue)
if (-not $netdataWasPresent) {
    $install = Start-Process msiexec.exe -ArgumentList "/qn /i `"$NetdataMsi`"" -Wait -PassThru
    if ($install.ExitCode -notin @(0, 1641, 3010)) { throw "Netdata MSI failed: $($install.ExitCode)" }
}

foreach ($path in @($pluginDirectory, $configDirectory, $backupDirectory)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
foreach ($target in @($collectorTarget, $collectorConfigTarget, $streamConfigTarget)) {
    if (Test-Path -LiteralPath $target) {
        Copy-Item -LiteralPath $target -Destination (Join-Path $backupDirectory "$(Split-Path $target -Leaf).$stamp") -Force
    }
}

$configuration = Get-Content -LiteralPath $CollectorConfig -Raw | ConvertFrom-Json
if ($configuration.structured_evidence_enabled -ne $false) {
    throw "Primary endpoint deployment requires structured_evidence_enabled=false."
}
if (-not [string]::IsNullOrWhiteSpace($configuration.intake) -or
    -not [string]::IsNullOrWhiteSpace($configuration.token_file)) {
    throw "Primary endpoint deployment cannot configure a second intake channel."
}
if (-not $configuration.url.StartsWith("https://", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The approved service operation must use HTTPS."
}

Stop-Service Netdata -Force -ErrorAction Stop
Copy-Item -LiteralPath $collectorSource -Destination $collectorTarget -Force
Copy-Item -LiteralPath $CollectorConfig -Destination $collectorConfigTarget -Force
Copy-Item -LiteralPath $StreamConfig -Destination $streamConfigTarget -Force
& icacls.exe $collectorConfigTarget $streamConfigTarget /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Netdata configuration ACL hardening failed." }

Start-Service Netdata
$deadline = [DateTime]::UtcNow.AddSeconds(60)
do {
    Start-Sleep -Seconds 2
    try {
        $charts = Invoke-RestMethod -Uri "http://127.0.0.1:19999/api/v1/charts" -TimeoutSec 3
        $collectorHealthy = [bool]($charts.charts.PSObject.Properties.Name -like "nawari.*")
    } catch {
        $collectorHealthy = $false
    }
} until ($collectorHealthy -or [DateTime]::UtcNow -ge $deadline)

if (-not $collectorHealthy) { throw "Netdata started but Nawari charts were not discovered." }
New-Item -Path "HKLM:\Software\Nawari\Netdata Extension" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\Software\Nawari\Netdata Extension" -Name Installed -Value 1 -Type DWord
Set-ItemProperty -Path "HKLM:\Software\Nawari\Netdata Extension" -Name NetdataInstalledByPackage -Value ([int](-not $netdataWasPresent)) -Type DWord
Write-Output "Netdata and the Nawari managed collector are healthy."
