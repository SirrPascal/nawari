# provisioning/endpoint/windows/nawari_nem_probe.ps1
# Nawari End-User Network Experience Monitoring (EU-NEM) - Windows 10/11 Probe
# Lightweight, non-privileged PowerShell diagnostic script for Zabbix Agent 2 Active Checks.

[CmdletBinding()]
param (
    [string]$Action = "all",
    [string]$CorporateDnsHost = "corp.kenya-airways.com",
    [string]$CorporateServiceHost = "10.2.1.10",
    [int]$CorporateServicePort = 389
)

$ErrorActionPreference = "SilentlyContinue"

function Get-GatewayDiagnostics {
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
    if (-not $defaultRoute) {
        return @{
            gateway_ip = "0.0.0.0"
            reachable = $false
            rtt_ms = 0.0
            loss_pct = 100.0
        }
    }

    $gwIp = $defaultRoute.NextHop
    $pingResults = Test-Connection -ComputerName $gwIp -Count 3 -TimeoutSeconds 1 -ErrorAction SilentlyContinue
    $successCount = ($pingResults | Where-Object { $_.Status -eq "Success" -or $_.ResponseTime -ne $null }).Count
    $lossPct = if ($pingResults.Count -gt 0) { [math]::Round(((3 - $successCount) / 3) * 100, 1) } else { 100.0 }
    
    $avgRtt = 0.0
    if ($successCount -gt 0) {
        $avgRtt = [math]::Round(($pingResults | Measure-Object -Property ResponseTime -Average).Average, 2)
    }

    return @{
        gateway_ip = $gwIp
        reachable = ($successCount -gt 0)
        rtt_ms = $avgRtt
        loss_pct = $lossPct
    }
}

function Get-DnsDiagnostics {
    param([string]$targetHost)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $success = $false
    try {
        $entry = [System.Net.Dns]::GetHostEntry($targetHost)
        if ($entry.AddressList.Count -gt 0) { $success = $true }
    } catch {
        $success = $false
    }
    $sw.Stop()

    $dnsServers = (Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses.Count -gt 0 }).ServerAddresses
    $primaryDns = if ($dnsServers.Count -gt 0) { $dnsServers[0] } else { "0.0.0.0" }

    return @{
        server_ip = $primaryDns
        target_host = $targetHost
        success = $success
        latency_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    }
}

function Get-WifiDiagnostics {
    $netsh = netsh wlan show interfaces
    $ssid = ""
    $bssid = ""
    $signal = 0.0
    $state = "disconnected"

    foreach ($line in ($netsh -split "`r`n")) {
        if ($line -match "^\s*SSID\s*:\s*(.+)$") { $ssid = $matches[1].Trim() }
        if ($line -match "^\s*BSSID\s*:\s*(.+)$") { $bssid = $matches[1].Trim() }
        if ($line -match "^\s*Signal\s*:\s*([0-9]+)%") { $signal = [double]$matches[1] }
        if ($line -match "^\s*State\s*:\s*(.+)$") { $state = $matches[1].Trim() }
    }

    return @{
        ssid = $ssid
        bssid = $bssid
        signal_pct = $signal
        state = $state
    }
}

function Get-ServiceTcpCheck {
    param([string]$hostName, [int]$port)
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $connect = $tcpClient.BeginConnect($hostName, $port, $null, $null)
    $wait = $connect.AsyncWaitHandle.WaitOne(1500, $false)
    $sw.Stop()
    $isOk = $false
    if ($wait) {
        try {
            $tcpClient.EndConnect($connect)
            $isOk = $true
        } catch { $isOk = $false }
    }
    $tcpClient.Close()
    return @{
        service_host = $hostName
        port = $port
        connected = $isOk
        rtt_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    }
}

function Get-RecentLifecycleEvents {
    # Check Event IDs 1074 (planned shutdown), 6006 (EventLog stop), 6008 (unexpected shutdown), 41 (Kernel-Power)
    $events = Get-WinEvent -FilterHashtable @{LogName='System'; Id=@(1074,6006,6008,41)} -MaxEvents 5 -ErrorAction SilentlyContinue
    $eventList = @()
    foreach ($evt in $events) {
        $eventList += @{
            event_id = $evt.Id
            time_created = $evt.TimeCreated.ToString("o")
            provider = $evt.ProviderName
        }
    }
    return $eventList
}

# Main Execution Dispatcher
switch ($Action) {
    "gateway" {
        Get-GatewayDiagnostics | ConvertTo-Json -Compress
    }
    "dns" {
        Get-DnsDiagnostics -targetHost $CorporateDnsHost | ConvertTo-Json -Compress
    }
    "wifi" {
        Get-WifiDiagnostics | ConvertTo-Json -Compress
    }
    "service" {
        Get-ServiceTcpCheck -hostName $CorporateServiceHost -port $CorporateServicePort | ConvertTo-Json -Compress
    }
    "lifecycle" {
        Get-RecentLifecycleEvents | ConvertTo-Json -Compress
    }
    default {
        $all = @{
            timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            gateway = Get-GatewayDiagnostics
            dns = Get-DnsDiagnostics -targetHost $CorporateDnsHost
            wifi = Get-WifiDiagnostics
            service = Get-ServiceTcpCheck -hostName $CorporateServiceHost -port $CorporateServicePort
            lifecycle = Get-RecentLifecycleEvents
        }
        $all | ConvertTo-Json -Compress
    }
}

