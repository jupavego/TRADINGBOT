<#
.SYNOPSIS
  Una pasada del vigilante del conjunto (T148, entregable 1): comprueba los cinco latidos y, si
  falta alguno desde hace rato, corre `servicio_continuo.ps1`.

.DESCRIPTION
  Lo llama la tarea programada «EIM - vigilante del conjunto» cada 5 minutos, que es quien lo hace
  distinto de los demás vigilantes: no es hijo de lo que vigila, así que un apagón del conjunto no
  se lo lleva por delante. Toda la decisión (qué falta, cuánto lleva caído, tope de intentos y
  espera creciente) vive en `eim/operation/fleet_watch.py`; esto solo elige el intérprete, fija la
  carpeta y deja la salida de cada pasada en data\operation\logs\fleet_watch.out.log.

  El registro se recorta solo: se conservan las últimas 2000 líneas (unos 7 días a 5 min).
  Código de salida 0 = nada que arreglar o arreglado; 1 = sigue caído y hay que mirarlo.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\vigilante_conjunto.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\vigilante_conjunto.ps1 -DryRun
#>
param(
  [string]$DataDir = "",
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not $DataDir) { $DataDir = Join-Path $v2 "data" }
$logs = Join-Path $DataDir "operation\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$env:PYTHONIOENCODING = "utf-8"

$argv = @("-m", "eim.operation.fleet_watch", "check", "--data-dir", $DataDir)
if ($DryRun) { $argv += "--dry-run" }
$salida = & $py $argv 2>&1
$rc = $LASTEXITCODE

$registro = Join-Path $logs "fleet_watch.out.log"
$sello = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Add-Content -LiteralPath $registro -Encoding utf8 -Value "$sello rc=$rc $($salida -join ' ')"
try {
  $lineas = @(Get-Content -LiteralPath $registro -Encoding utf8)
  if ($lineas.Count -gt 2000) {
    Set-Content -LiteralPath $registro -Encoding utf8 -Value $lineas[-2000..-1]
  }
} catch { }

$salida
exit $rc
