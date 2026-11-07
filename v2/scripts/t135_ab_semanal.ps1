<#
.SYNOPSIS
  Informe semanal del A/B de M8 (T135): actualiza su copia de datos y escribe el informe en
  reports\t135_ab\. No toca el almacen vivo, los perfiles ni la API.

.DESCRIPTION
  1. Toma los contextos de la copia de seguridad completa mas reciente (backups\eim_*).
  2. Baja las velas que falten a backups\t135_ab, por la cola de trabajos pesados.
  3. Calcula el informe, tambien por la cola. Mientras no se cumplan los minimos del pre-registro,
     el estado es EN CURSO y las cifras son provisionales.

  -Instalar registra la tarea semanal (lunes, 02:30 UTC); -Quitar la borra.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\t135_ab_semanal.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\t135_ab_semanal.ps1 -Instalar
#>
param([switch]$Instalar, [switch]$Quitar)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$copia = Join-Path $v2 "backups\t135_ab"
$tarea = "EIM - informe semanal A-B M8 (T135)"

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $tarea -Confirm:$false
  Write-Host "Tarea quitada: $tarea"
  exit 0
}
if ($Instalar) {
  # 02:30 UTC del lunes, despues de la copia diaria de las 00:00 UTC, en la hora local del equipo.
  $utc = [DateTime]::SpecifyKind([DateTime]"2026-11-09T02:30:00", [DateTimeKind]::Utc)
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"")
  $cuando = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek $utc.ToLocalTime().DayOfWeek `
    -At $utc.ToLocalTime()
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes | Out-Null
  Write-Host "Tarea registrada: $tarea"
  exit 0
}

$ultima = Get-ChildItem (Join-Path $v2 "backups") -Directory -Filter "eim_*" |
  Where-Object { Test-Path (Join-Path $_.FullName "paper.duckdb") } |
  Sort-Object Name -Descending | Select-Object -First 1
if (-not $ultima) { Write-Error "no hay copia de seguridad con paper.duckdb" }
Copy-Item (Join-Path $ultima.FullName "paper.duckdb") (Join-Path $copia "paper.duckdb") -Force
Write-Host "contextos de $($ultima.Name)"

function Cola([string]$nombre, [int]$ram, [string[]]$orden) {
  & $py -m eim.operation.jobs --data-dir $datos submit --name $nombre --cwd $v2 --min-ram-mb $ram -- $py @orden
  if ($LASTEXITCODE -ne 0) { Write-Error "$nombre termino con codigo $LASTEXITCODE" }
}

Cola "t135-historia" 1000 @("scripts/t131_history.py", "--out", $copia, "--from", "2023-01-01",
                            "--backups", (Join-Path $v2 "backups"))
Cola "t135-informe" 2500 @("scripts/t135_ab_m8.py", "report", "--data", $copia)
