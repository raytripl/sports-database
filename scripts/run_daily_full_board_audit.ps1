$ErrorActionPreference = "Stop"
$Repo = if ($env:SPORTS_HUB_REPO) { $env:SPORTS_HUB_REPO } else { "C:\Users\raymo\Documents\sports-database" }
Set-Location $Repo

$Log = "$Repo\logs\full_board_audit.log"
$Python = "$Repo\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

New-Item -ItemType Directory -Force "$Repo\logs" | Out-Null
"`n[$(Get-Date -Format o)] Starting full-board postgame audit" | Out-File -Append -FilePath $Log

try {
    # Updater libraries can write warnings to stderr. Preserve the complete
    # process exit code instead of turning the first warning into an exception.
    $ErrorActionPreference = "Continue"
    & $Python update_all.py --sport wnba >> $Log 2>&1
    $WnbaExit = $LASTEXITCODE
    & $Python update_all.py --sport mlb >> $Log 2>&1
    $MlbExit = $LASTEXITCODE

    $ThroughDate = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
    & $Python -m src.audits.run_daily_audits --through-date $ThroughDate >> $Log 2>&1
    $AuditExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"

    if ($AuditExit -ne 0) { throw "Audit runner exited with $AuditExit" }
    "[$(Get-Date -Format o)] Audit completed through $ThroughDate; WNBA update=$WnbaExit MLB update=$MlbExit" |
        Out-File -Append -FilePath $Log
}
catch {
    $ErrorActionPreference = "Stop"
    "[$(Get-Date -Format o)] SAFE FAILURE: $($_.Exception.Message)" | Out-File -Append -FilePath $Log
    exit 1
}
