$ErrorActionPreference = "Stop"
$Repo = "C:\Users\raymo\Documents\sports-database"
Set-Location $Repo

$log = "$Repo\logs\prizepicks_hourly.log"
$python = "$Repo\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

New-Item -ItemType Directory -Force "$Repo\logs" | Out-Null
"`n[$(Get-Date -Format o)] Starting hourly PrizePicks capture" | Out-File -Append -FilePath $log
try {
    & $python -m src.automation.prizepicks_hourly *>> $log
    if ($LASTEXITCODE -ne 0) { throw "Capture exited with $LASTEXITCODE" }
    "[$(Get-Date -Format o)] Capture completed" | Out-File -Append -FilePath $log
}
catch {
    "[$(Get-Date -Format o)] SAFE FAILURE: $($_.Exception.Message)" | Out-File -Append -FilePath $log
    exit 1
}
