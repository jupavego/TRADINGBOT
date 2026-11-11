<#
.SYNOPSIS
  Colector del indice DVOL de Deribit (T165): cada hora refresca la volatilidad implicita de BTC
  en el almacen vivo. No arranca ningun servicio nuevo ni toca los que ya corren.

  Solo BTC: es el alcance de este trabajo (decision del usuario, 2026-11-11). Otra moneda hay que
  pedirla a mano con -Monedas, y medirla exigiria su propio pre-registro.

.DESCRIPTION
  Ejecuta `python -m eim.data.dvol` con prioridad de lote (IDLE, `eim.operation.priority`), para no
  competir con la captura HFT ni con el broker simulado. Cada pasada es incremental: pide solo lo
  que falta desde la ultima vela guardada menos 24 h, asi que dura segundos y gasta unos pocos MB.

  La serie queda en `data\dvol\symbol=BTC\timeframe=1h\` y cada pasada deja una linea en
  `data\operation\logs\dvol.log`, tambien si falla, con las filas y la cobertura resultantes.

  Por que cada hora: el DVOL publica velas de 60 min y el pronostico de T165 usa la que cierra a
  las 00:00 UTC. Un dato de mas de un dia de antiguedad no sirve (`daily_implied_var` lo descarta),
  y con el DVOL de ayer el modelo es PEOR que el HAR sin DVOL: ver `reports\t165_dvol.md`.

  -Instalar registra la tarea horaria; -Quitar la borra. Instalala desde la carpeta principal
  (`C:\Users\jo\Desktop\JP\TRADINGBOT\v2`), que es la que corre los servicios, no desde un worktree.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\dvol_colector.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\dvol_colector.ps1 -Instalar
  powershell -ExecutionPolicy Bypass -File v2\scripts\dvol_colector.ps1 -Quitar
#>
param([switch]$Instalar, [switch]$Quitar, [string]$Monedas = "BTC")
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - colector DVOL de Deribit (T165)"
$registro = Join-Path $datos "operation\logs\dvol.log"

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
  if (-not (Test-Path $py)) { throw "no existe $py; instala desde la carpeta principal" }
  # Al minuto 10 de cada hora: la vela horaria del DVOL ya cerro y esta publicada.
  $primera = (Get-Date).Date.AddHours((Get-Date).Hour).AddMinutes(10)
  if ($primera -lt (Get-Date)) { $primera = $primera.AddHours(1) }
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" " +
    "-Monedas $Monedas")
  $cuando = New-ScheduledTaskTrigger -Once -At $primera `
    -RepetitionInterval (New-TimeSpan -Hours 1)
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes `
    -Description ("EIM T165: refresca el indice DVOL de Deribit (publico, sin clave) en " +
      "data\dvol\. Incremental, en prioridad de lote. Registro en data\operation\logs\dvol.log.") `
    -Force | Out-Null
  Write-Host "Tarea registrada: '$tarea' (cada hora, primera a las $primera)."
  Write-Host "Probarla ahora: Start-ScheduledTask -TaskName '$tarea'"
  exit 0
}

try {
  if (-not (Test-Path $py)) {
    throw "no existe ${py}; este script corre desde la carpeta principal, no desde un worktree"
  }
  $salida = & $py -m eim.operation.priority run batch -- `
    $py -m eim.data.dvol --data $datos --currency $Monedas 2>&1
  if ($LASTEXITCODE -ne 0) { throw "codigo $LASTEXITCODE : $($salida -join ' ')" }
  # Hay que asignar antes de recorrer: en PowerShell 5.1 `ConvertFrom-Json` no desenrolla el
  # arreglo por la tuberia, y `$_` llegaria siendo la lista entera.
  $filas = ConvertFrom-Json ($salida | Out-String)
  $resumen = ($filas | ForEach-Object {
    "$($_.currency) filas=$($_.rows) nuevas=$($_.fetched) cobertura=$($_.coverage) hasta=$($_.last)"
  }) -join " | "
  Anota "bien: $resumen"
  Write-Host $resumen
} catch {
  Anota "FALLO: $_"
  exit 1
}
