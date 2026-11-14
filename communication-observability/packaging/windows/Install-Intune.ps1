[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$GatewayUrl,
    [Parameter(Mandatory)] [string]$EnrollmentTokenFile,
    [string]$NawariMsi = "$PSScriptRoot\NawariEndpointAgent-x64.msi",
    [string]$NetdataMsi = "$PSScriptRoot\Netdata-x64.msi",
    [Parameter(Mandatory)] [string]$NawariMsiSha256,
    [Parameter(Mandatory)] [string]$NetdataMsiSha256
)

$ErrorActionPreference = "Stop"
$agentService = "NawariEndpointAgent"
$netdataService = "Netdata"
$serviceKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$agentService"

function Assert-Artifact([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Required artifact is absent: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $ExpectedHash) { throw "SHA-256 mismatch for $Path" }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne "Valid") { throw "Authenticode validation failed for $Path: $($signature.Status)" }
}

function Invoke-Msi([string]$Arguments) {
    $process = Start-Process msiexec.exe -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 1641, 3010)) {
        throw "Windows Installer failed with exit code $($process.ExitCode)."
    }
}

if (-not $GatewayUrl.StartsWith("https://", [StringComparison]::OrdinalIgnoreCase)) {
    throw "GatewayUrl must use HTTPS."
}

Assert-Artifact $NawariMsi $NawariMsiSha256
Assert-Artifact $NetdataMsi $NetdataMsiSha256

$netdataWasPresent = [bool](Get-Service $netdataService -ErrorAction SilentlyContinue)
if (-not $netdataWasPresent) {
    Invoke-Msi "/i `"$NetdataMsi`" /qn /norestart"
}

try {
    Invoke-Msi "/i `"$NawariMsi`" /qn /norestart"

    $agentExe = Join-Path $env:ProgramFiles "Nawari\Endpoint Agent\nawari-agent.exe"
    if (-not (Test-Path -LiteralPath $agentExe)) { throw "Nawari agent executable was not installed." }

    $token = (Get-Content -LiteralPath $EnrollmentTokenFile -Raw).Trim()
    if ($token.Length -lt 16) { throw "Enrollment token file is empty or invalid." }
    $token | & $agentExe credential-store
    if ($LASTEXITCODE -ne 0) { throw "DPAPI credential storage failed." }
    $credentialPath = "$env:ProgramData\Nawari\Endpoint Agent\credential.bin"
    & icacls.exe $credentialPath /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Credential ACL hardening failed." }

    $environment = @(
        "NAWARI_GATEWAY_URL=$GatewayUrl",
        "NAWARI_ENVIRONMENT=PHYSICAL_PRODUCTION",
        "NAWARI_STATE_DIR=$env:ProgramData\Nawari\Endpoint Agent",
        "NAWARI_SPOOL_DIR=$env:ProgramData\Nawari\Endpoint Agent\spool"
    )
    Set-ItemProperty -Path $serviceKey -Name Environment -Type MultiString -Value $environment

    Set-Service -Name $agentService -StartupType Automatic
    Start-Service -Name $agentService
    Set-Service -Name $netdataService -StartupType Automatic
    Start-Service -Name $netdataService

    sc.exe failure $agentService reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    sc.exe failureflag $agentService 1 | Out-Null

    if ((Get-Service $agentService).Status -ne "Running") { throw "Nawari service did not reach Running." }
    if ((Get-Service $netdataService).Status -ne "Running") { throw "Netdata service did not reach Running." }
}
catch {
    Invoke-Msi "/x `"$NawariMsi`" /qn /norestart"
    throw
}
finally {
    Remove-Item -LiteralPath $EnrollmentTokenFile -Force -ErrorAction SilentlyContinue
    Remove-Variable token -ErrorAction SilentlyContinue
}

New-Item -Path "HKLM:\Software\Nawari\Endpoint Deployment" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\Software\Nawari\Endpoint Deployment" -Name "ManagedPackage" -Value 1 -Type DWord
Set-ItemProperty -Path "HKLM:\Software\Nawari\Endpoint Deployment" -Name "NetdataInstalledByPackage" -Value ([int](-not $netdataWasPresent)) -Type DWord
