# provisioning/endpoint/windows/Deploy-NawariNEM-Intune.ps1
# Kenya Airways IT Endpoint Operations - Microsoft Intune Deployment Package
# Deploys Zabbix Agent 2 with EU-NEM Active Probing and Auto-Registration.

[CmdletBinding()]
param(
    [string]$ZabbixServer = "10.0.0.10:10051",
    [string]$HostMetadata = "nawari_nem",
    [string]$InstallDir = "C:\Program Files\Zabbix Agent 2"
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================"
Write-Host "KENYA AIRWAYS EU-NEM INTUNE AGENT 2 DEPLOYMENT ENGINE"
Write-Host "Target ServerActive: $ZabbixServer"
Write-Host "Host Metadata:       $HostMetadata"
Write-Host "Destination:         $InstallDir"
Write-Host "======================================================================"

# 1. Check Elevation
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This deployment script must execute with elevated Administrator privileges."
}

# 2. Verify or Install Zabbix Agent 2 MSI
$service = Get-Service -Name "Zabbix Agent 2" -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "[INSTALL] Zabbix Agent 2 service not found. Installing MSI..."
    $msiPath = Join-Path $PSScriptRoot "zabbix_agent2-7.4.0-windows-amd64.msi"
    if (-not (Test-Path $msiPath)) {
        Write-Host "[DOWNLOAD] Downloading official Zabbix 7.4 Agent 2 MSI..."
        $downloadUrl = "https://cdn.zabbix.com/zabbix/binaries/stable/7.4/7.4.0/zabbix_agent2-7.4.0-windows-amd64-openssl.msi"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $msiPath
    }
    
    $installArgs = "/i `"$msiPath`" /qn SERVERACTIVE=`"$ZabbixServer`" HOSTMETADATA=`"$HostMetadata`" ENABLEPATH=1 /norestart"
    Start-Process -FilePath "msiexec.exe" -ArgumentList $installArgs -Wait
    Write-Host "[INSTALL] MSI installation completed."
} else {
    Write-Host "[STATUS] Zabbix Agent 2 is already installed."
}

# 3. Create Scripts Directory and Deploy Probe
$scriptsDir = Join-Path $InstallDir "scripts"
if (-not (Test-Path $scriptsDir)) {
    New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
}

$probeSource = Join-Path $PSScriptRoot "nawari_nem_probe.ps1"
$probeDest = Join-Path $scriptsDir "nawari_nem_probe.ps1"
if (Test-Path $probeSource) {
    Copy-Item -Path $probeSource -Destination $probeDest -Force
    Write-Host "[DEPLOY] Copied probe script to $probeDest"
}

# 4. Configure zabbix_agent2.conf
$confFile = Join-Path $InstallDir "zabbix_agent2.conf"
if (Test-Path $confFile) {
    Write-Host "[CONFIG] Injecting EU-NEM settings and UserParameters..."
    $confContent = Get-Content $confFile -Raw

    # Update ServerActive and HostMetadata
    $confContent = $confContent -replace "(?m)^ServerActive=.*$", "ServerActive=$ZabbixServer"
    $confContent = $confContent -replace "(?m)^#?\s*HostMetadata=.*$", "HostMetadata=$HostMetadata"
    $confContent = $confContent -replace "(?m)^#?\s*EnablePersistentBuffer=.*$", "EnablePersistentBuffer=1"
    $confContent = $confContent -replace "(?m)^#?\s*PersistentBufferPeriod=.*$", "PersistentBufferPeriod=24h"

    # Append UserParameter if missing
    if ($confContent -notmatch "nawari\.nem\.all") {
        $userParams = @"

# --- Nawari EU-NEM Active Diagnostics ---
UserParameter=nawari.nem.all,powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$probeDest" all
UserParameter=nawari.nem.gateway,powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$probeDest" gateway
UserParameter=nawari.nem.dns,powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$probeDest" dns
UserParameter=nawari.nem.wifi,powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$probeDest" wifi
UserParameter=nawari.nem.service,powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$probeDest" service
"@
        $confContent += $userParams
    }

    Set-Content -Path $confFile -Value $confContent -Encoding Ascii
    Write-Host "[CONFIG] zabbix_agent2.conf successfully updated."
}

# 5. Restart Zabbix Agent 2 Service
Write-Host "[SERVICE] Restarting Zabbix Agent 2 service..."
Restart-Service -Name "Zabbix Agent 2" -Force
Write-Host "[SUCCESS] Nawari EU-NEM agent deployment completed successfully."

