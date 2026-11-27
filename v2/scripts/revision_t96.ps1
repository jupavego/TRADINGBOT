<#
.SYNOPSIS
  Revision programada para decidir T96 (decision del usuario en T95, 2026-11-26):
  calibra los pesos del ranking fuera de muestra, repite el placebo y aplica la regla de
  PLAN\notas\T96_revision.md sobre el registro de intentos hacia adelante.

.DESCRIPTION
  Una sola vez, el 2026-12-29 a las 09:00 hora local (si el equipo estaba apagado, en cuanto se
  enciende). Prioridad baja. Escribe en data\scanner (rank_weights.json si se adoptan pesos,
  placebo.json, placebo_revision.md, revision_t96.md/.json) y copia el informe a
  TRADINGBOT\_revision_t96.md para leerlo facil. No toca archivos del repositorio ni T31.
  Cada paso deja una linea en data\operation\logs\revision_t96.log.

  -Instalar registra la tarea; -Quitar la borra. Instalar SOLO en la laptop.
#>
param([switch]$Instalar, [switch]$Quitar)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$raiz = Split-Path -Parent $v2
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - revision para decidir T96 (2026-12-29)"
$registro = Join-Path $datos "operation\logs\revision_t96.log"
$env:PYTHONIOENCODING = "utf-8"

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
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"")
  $cuando = New-ScheduledTaskTrigger -Once -At ([DateTime]"2026-12-29T09:00:00")
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes -Force | Out-Null
  Write-Host "Tarea registrada: $tarea"
  exit 0
}

function Paso([string]$nombre, [string[]]$orden) {
  $ErrorActionPreference = "Continue"   # avisos por stderr de Python no son un fallo
  $salida = & $py -m eim.operation.priority run batch -- $py @orden 2>&1
  $codigo = $LASTEXITCODE
  $texto = (($salida | Out-String).Trim() -replace "\s+", " ")
  if ($texto.Length -gt 900) { $texto = $texto.Substring($texto.Length - 900) }
  Anota "$nombre (codigo $codigo): $texto"
  return $codigo
}

try {
  Push-Location $v2
  Paso "calibrar pesos" @("-m", "eim.scanner", "--data-dir", $datos, "calibrate") | Out-Null
  $p = Paso "placebo" @("scripts\scanner_placebo.py", "--data-dir", $datos,
    "--out", (Join-Path $datos "scanner\placebo_revision.md"),
    "--log", (Join-Path $datos "scanner\placebo_revision_log.txt"))
  if ($p -ne 0) { Anota "AVISO: el placebo fallo; la revision usa el ultimo placebo guardado" }
  $informe = Join-Path $datos "scanner\revision_t96.md"
  $r = Paso "revision" @("scripts\scanner_revision.py", "--data-dir", $datos, "--out", $informe,
    "--summary", (Join-Path $raiz "_revision_t96.txt"))
  Pop-Location
  if ($r -ne 0) { throw "la revision fallo (codigo $r)" }
  Copy-Item $informe (Join-Path $raiz "_revision_t96.md") -Force
  Anota "bien: informe en _revision_t96.md"
} catch {
  Anota "FALLO: $_"
  exit 1
}
