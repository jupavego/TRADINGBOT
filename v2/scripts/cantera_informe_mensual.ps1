<#
.SYNOPSIS
  Informe mensual de la cantera (T172): lo escribe solo cuando pasa una revision pre-registrada
  (dias 30, 61, 91, 121, 152 y 182 desde el alta de cantera_v1) y el ultimo informe no la recoge.
  Al llegar a la fecha limite (dia 182) escribe el cierre de la fase. No toca la cantera, la API,
  la sintesis ni los libros de T31.

.DESCRIPTION
  Corre a diario a las 01:30 UTC con prioridad baja (`eim.operation.priority run batch`). Lee el
  libro de la cantera en solo lectura; si el servicio lo tiene abierto, de la copia diaria mas
  reciente (00:00 UTC). Como la copia del dia de la revision es anterior a la hora de la revision,
  el informe sale como pronto el dia siguiente: es lo esperado.

  Deja el informe en reports\nursery\cantera_<fecha>.md (+ .json y latest.json, que lee la
  auditoria semanal) y los hechos de aprendizaje en data\library\digital\nursery_facts.jsonl.
  Las lineas para BACKLOG y las propuestas (decision del usuario) quedan en el informe: las revisa el usuario.
  Cada pasada deja una linea en data\operation\logs\cantera_informe.log, tambien si falla.

  Instalar solo en el equipo que corre la cantera (EIM_NURSERY=1). -Instalar registra la tarea
  diaria; -Quitar la borra.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\cantera_informe_mensual.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\cantera_informe_mensual.ps1 -Instalar
#>
param([switch]$Instalar, [switch]$Quitar)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - informe mensual de la cantera (T172)"
$registro = Join-Path $datos "operation\logs\cantera_informe.log"

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
  # 01:30 UTC, despues de la copia diaria de las 00:00 UTC, en la hora local del equipo.
  $utc = [DateTime]::SpecifyKind([DateTime]"2026-11-20T01:30:00", [DateTimeKind]::Utc)
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
  $salida = & $py -m eim.operation.priority run batch -- $py -m eim.nursery report --si-toca 2>&1
  $codigo = $LASTEXITCODE
  Pop-Location
  $texto = ($salida | Out-String).Trim() -replace "\s+", " "
  if ($codigo -ne 0) { throw "codigo $codigo : $texto" }
  Anota "bien: $texto"
} catch {
  Anota "FALLO: $_"
  exit 1
}
