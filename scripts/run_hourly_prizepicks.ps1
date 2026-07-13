$ErrorActionPreference = "Stop"
$Repo = "C:\Users\raymo\Documents\sports-database"
Set-Location $Repo

$log = "$Repo\logs\prizepicks_hourly.log"
$python = "$Repo\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

New-Item -ItemType Directory -Force "$Repo\logs" | Out-Null
"`n[$(Get-Date -Format o)] Starting hourly PrizePicks capture" | Out-File -Append -FilePath $log
try {
    # Downloader retry warnings are intentionally written to stderr. They must
    # be logged without PowerShell converting the first warning into a
    # terminating ErrorRecord before Python can use its manual-export fallback.
    $ErrorActionPreference = "Continue"
    & $python -m src.automation.prizepicks_hourly >> $log 2>&1
    $captureExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($captureExitCode -ne 0) { throw "Capture exited with $captureExitCode" }
    "[$(Get-Date -Format o)] Capture completed" | Out-File -Append -FilePath $log
}
catch {
    $ErrorActionPreference = "Stop"
    "[$(Get-Date -Format o)] SAFE FAILURE: $($_.Exception.Message)" | Out-File -Append -FilePath $log
    exit 1
}
