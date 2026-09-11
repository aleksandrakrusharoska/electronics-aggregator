# Network watchdog: periodically verifies GitHub Actions connectivity and
# attempts self-healing (DNS flush + adapter restart) if it's unreachable.
# Written after a ~4-day outage where self-hosted runner jobs sat "queued"
# for 24h and auto-cancelled — runner logs showed repeated DNS failures
# ("No such host is known" for *.actions.githubusercontent.com) despite a
# working network adapter, meaning the OS never noticed anything was wrong
# and never recovered on its own.
#
# Run this via Task Scheduler on a short interval (e.g. every 10 minutes).
# Logs to network_watchdog.log next to this script.

$logFile = Join-Path $PSScriptRoot "network_watchdog.log"
$testHost = "pipelinesghubeus25.actions.githubusercontent.com"
$adapterAlias = "Wi-Fi 2"

function Write-Log($message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "[$timestamp] $message"
}

$resolved = $false
try {
    $null = Resolve-DnsName -Name $testHost -ErrorAction Stop
    $resolved = $true
} catch {
    Write-Log "DNS resolution FAILED for $testHost : $($_.Exception.Message)"
}

if (-not $resolved) {
    Write-Log "Attempting recovery: flushing DNS cache"
    ipconfig /flushdns | Out-Null

    Start-Sleep -Seconds 3
    try {
        $null = Resolve-DnsName -Name $testHost -ErrorAction Stop
        Write-Log "Recovered after DNS flush alone"
        exit 0
    } catch {
        Write-Log "Still failing after DNS flush — restarting adapter '$adapterAlias'"
    }

    try {
        Restart-NetAdapter -Name $adapterAlias -Confirm:$false -ErrorAction Stop
        Start-Sleep -Seconds 15
        $null = Resolve-DnsName -Name $testHost -ErrorAction Stop
        Write-Log "Recovered after adapter restart"
    } catch {
        Write-Log "Still failing after adapter restart: $($_.Exception.Message) — needs manual attention"
    }
}
