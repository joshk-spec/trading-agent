$ErrorActionPreference = "Stop"
Set-Location "C:\Users\josh\trading-agent"

$logDir = "C:\Users\josh\trading-agent\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logFile = Join-Path $logDir "trade_$timestamp.log"

& "C:\Users\josh\.local\bin\claude.exe" -p "/trade" --permission-mode bypassPermissions *>> $logFile
