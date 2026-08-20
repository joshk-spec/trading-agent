# Local scheduled-task runner for /trade.
#
# DISABLED 2026-08-20. Trading moved to the cloud routine
# "trading-agent-daily-session" (claude.ai/code/routines), which runs weekdays
# during market hours regardless of whether this machine is on.
#
# This script and the Windows task "TradingAgent Daily Trade" are a SECOND,
# independent agent trading the same account 793973603. Two agents racing on
# the same state/*.json means a corrupted day-trade count (PDT is a 90-day
# account restriction, not a warning), positions opened without knowledge of
# each other's exposure, and MAX_CONCURRENT / MAX_SYMBOL_EXP silently breached.
# It also ran with --permission-mode bypassPermissions against live money.
#
# The Windows task could not be disabled without administrator rights, so this
# guard stops the run here instead. To remove the task properly, in an ELEVATED
# PowerShell:
#     Disable-ScheduledTask -TaskName "TradingAgent Daily Trade"
#     # or, to delete it outright:
#     Unregister-ScheduledTask -TaskName "TradingAgent Daily Trade" -Confirm:$false
#
# To deliberately re-enable local running, set this to $false AND first disable
# the cloud routine — never both at once.
$LocalRunnerDisabled = $true

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\josh\trading-agent"

$logDir = "C:\Users\josh\trading-agent\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logFile = Join-Path $logDir "trade_$timestamp.log"

if ($LocalRunnerDisabled) {
    "[$timestamp] SKIPPED - local runner disabled; the cloud routine owns this account. No session started." |
        Out-File -FilePath $logFile -Encoding utf8
    exit 0
}

& "C:\Users\josh\.local\bin\claude.exe" -p "/trade" --permission-mode bypassPermissions *>> $logFile
