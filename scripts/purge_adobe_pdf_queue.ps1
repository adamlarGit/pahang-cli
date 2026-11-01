<#
.SYNOPSIS
    Clears stuck ("zombie") jobs from the Adobe PDF print queue.

.DESCRIPTION
    WHY THIS EXISTS
    The full-report postprocessing step can print Word documents through the
    "Adobe PDF" virtual printer (Acrobat 11). When it does, the Print Spooler
    starts its own copy of acrodist.exe and acrotray.exe in Session 0 (the
    background service session, not your desktop). That Distiller can deadlock,
    leaving jobs stuck at "Deleting, Printing, Retained" or "Deleting, Spooling".
    See docs/research/adobe_pdf_spooler_session0_deadlock_investigation.md.

    Deleting files from spool\PRINTERS doesn't fix this. In the 2026-11-01
    incident that folder was empty and the jobs were held in the spooler's
    memory. The Session-0 acrodist has to be killed and the spooler restarted.

    If jobs come back after a cleanup, check the submitted time
    (Get-PrintJob -PrinterName 'Adobe PDF'). New jobs mean something is still
    printing, usually an open pahang-cli run. Close it before purging again.

    WHAT IT DOES
      1. Re-launches itself as Administrator if needed (UAC prompt).
      2. Lists the current jobs on the queue.
      3. Kills acrodist, acrotray, splwow64 and PrintIsolationHost in all
         sessions, including Session 0.
      4. Force-stops the Print Spooler (kills spoolsv.exe if it hangs).
      5. Deletes everything in C:\Windows\System32\spool\PRINTERS.
      6. Starts the spooler and reports the remaining job count.
      7. Restarts AcroTray as your normal (non-elevated) user, unless
         -NoAcroTray is given.

    A transcript is written to %TEMP%\purge_adobe_pdf_queue.log.

    WARNING: this kills jobs on every printer, not just Adobe PDF, because
    stopping the spooler and clearing the spool folder affects every queue.
    Close Word and stop any pahang-cli run first.

.PARAMETER PrinterName
    Queue to report on before and after. Defaults to "Adobe PDF".

.PARAMETER NoAcroTray
    Don't restart AcroTray afterwards.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\purge_adobe_pdf_queue.ps1

    Run from a normal (non-admin) prompt. Accept the UAC prompt; the elevated
    window does the purge, then AcroTray is restarted as you.

.EXAMPLE
    .\scripts\purge_adobe_pdf_queue.ps1 -NoAcroTray
#>
param(
    [string]$PrinterName = 'Adobe PDF',
    [switch]$NoAcroTray,
    [switch]$Elevated  # internal: set when the script re-launches itself
)

$AcroTrayPath = 'C:\Program Files (x86)\Adobe\Acrobat 11.0\Acrobat\acrotray.exe'
$LogPath = Join-Path $env:TEMP 'purge_adobe_pdf_queue.log'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

# --- Non-elevated caller: relaunch elevated, then restart AcroTray as this user ---
if (-not $isAdmin) {
    Write-Host "Requesting administrator rights (UAC prompt)..." -ForegroundColor Cyan
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -PrinterName `"$PrinterName`" -NoAcroTray -Elevated"
    try {
        Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $argList -ErrorAction Stop
    } catch {
        Write-Host "Elevation was cancelled or failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    if (Test-Path $LogPath) { Get-Content $LogPath }
    if (-not $NoAcroTray -and (Test-Path $AcroTrayPath)) {
        Start-Process $AcroTrayPath
        Write-Host "AcroTray restarted in your user session." -ForegroundColor Green
    }
    exit 0
}

# --- Elevated: do the purge ---
Start-Transcript -Path $LogPath -Force | Out-Null

Write-Host "--- before: '$PrinterName' jobs ---"
Get-PrintJob -PrinterName $PrinterName -ErrorAction SilentlyContinue |
    Format-Table Id, DocumentName, JobStatus, SubmittedTime -AutoSize | Out-String -Width 300

foreach ($name in 'acrodist', 'acrotray', 'splwow64', 'PrintIsolationHost') {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "kill $($_.Name) pid=$($_.Id) session=$($_.SessionId)"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

Stop-Service Spooler -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Process spoolsv -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Write-Host "spooler: $((Get-Service Spooler).Status)"

$spoolDir = 'C:\Windows\System32\spool\PRINTERS'
$files = @(Get-ChildItem $spoolDir -Force -ErrorAction SilentlyContinue)
Write-Host "spool files found: $($files.Count)"
$files | Remove-Item -Force -Recurse -ErrorAction Continue
Write-Host "spool files remaining: $(@(Get-ChildItem $spoolDir -Force -ErrorAction SilentlyContinue).Count)"

Start-Service Spooler
Start-Sleep -Seconds 3
Write-Host "--- after ---"
Write-Host "spooler: $((Get-Service Spooler).Status)"
Write-Host "'$PrinterName' jobs: $(@(Get-PrintJob -PrinterName $PrinterName -ErrorAction SilentlyContinue).Count)"

if (-not $NoAcroTray -and -not $Elevated -and (Test-Path $AcroTrayPath)) {
    # Started directly from an admin prompt: AcroTray will run elevated.
    Start-Process $AcroTrayPath
    Write-Host "AcroTray restarted (elevated)."
}

Stop-Transcript | Out-Null
