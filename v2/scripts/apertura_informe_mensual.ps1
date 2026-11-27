<#
.SYNOPSIS
  Informe de seguimiento del patron de apertura (T211): acumula las aperturas del mes y las mide
  contra el pre-registro congelado `prereg_apertura_v1`. No toca el libro de T31, la cantera, la
  sintesis ni la API: solo lee el almacen de velas y escribe en data\apertura y reports\apertura.

.DESCRIPTION
  Corre a diario a las 02:10 UTC con prioridad baja (`eim.operation.priority run batch`). El
  evaluador es retrospectivo e idempotente: cada apertura se guarda una sola vez en
  data\apertura\aperturas.jsonl, asi que repetir la corrida no duplica nada y una pasada perdida
  se recupera sola en la siguiente (mientras el almacen de 1 m cubra esos dias).

  Deja el informe en reports\apertura\apertura_<fecha>.md y el resumen en latest.json. El
  veredicto no llega antes del 2027-11-24 por pre-registro; hasta entonces el informe dice cuanta
  muestra falta. Cada pasada deja una linea en data\operation\logs\apertura_informe.log, tambien
  si falla.

  -Instalar registra la tarea diaria; -Quitar la borra. Instalar solo en el equipo que captura
  velas de 1 m sin huecos.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\apertura_informe_mensual.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\apertura_informe_mensual.ps1 -Instalar
#>
param([switch]$Instalar, [switch]$Quitar)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - seguimiento del patron de apertura (T211)"
$registro = Join-Path $datos "operation\logs\apertura_informe.log"

function Anota([string]$texto) {
  $ahora = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $registro) | Out-Null
  Add-Content -LiteralPath $registro -Value "$ahora $texto" -Encoding UTF8
}

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $tarea -Confirm:$false
  Write-Host "Tarea quitada: $tarea"
  exit 0
}
if ($Instalar) {
  # 02:10 UTC: despues de la copia diaria (00:00) y del informe de la cantera (01:30).
  $utc = [DateTime]::SpecifyKind([DateTime]"2026-11-24T02:10:00", [DateTimeKind]::Utc)
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"")
  $cuando = New-ScheduledTaskTrigger -Daily -At $utc.ToLocalTime()
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes | Out-Null
  Write-Host "Tarea registrada: $tarea"
  exit 0
}

try {
  Push-Location $v2
  $salida = & $py -m eim.operation.priority run batch -- $py -m eim.analytics.apertura_report 2>&1
  $codigo = $LASTEXITCODE
  Pop-Location
  $texto = ($salida | Out-String).Trim() -replace "\s+", " "
  if ($codigo -ne 0) { throw "codigo $codigo : $texto" }
  Anota "bien: $texto"
} catch {
  Anota "FALLO: $_"
  exit 1
}
