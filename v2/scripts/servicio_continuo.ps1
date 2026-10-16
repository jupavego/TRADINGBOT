<#
.SYNOPSIS
  Deja corriendo sin parar el servicio del EIM (T48): vigilante -> API + operación en papel +
  bróker simulado (15 m, 1 h y 4 h). Con -ConWeb también la interfaz en http://127.0.0.1:5173.

.DESCRIPTION
  El vigilante (`python -m eim.operation run --execution paper`) relanza la API si se cae o si su
  latido se detiene. Dentro de la API, el bróker simulado analiza cada vela cerrada y abre
  operaciones en papel; nunca envía órdenes reales. Si ya hay algo escuchando en el puerto, no se
  lanza otra copia (se puede ejecutar varias veces sin duplicar).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1 -ConWeb
#>
param(
  [switch]$ConWeb,
  [string]$DataDir = "",
  [int]$Puerto = 8000
)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not $DataDir) { $DataDir = Join-Path $v2 "data" }
$logs = Join-Path $DataDir "operation\logs"
New-Item -ItemType Directory -Force $logs | Out-Null

function Escuchando([int]$p) {
  [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

if (Escuchando $Puerto) {
  Write-Host "Ya hay un servicio en el puerto ${Puerto}: no se lanza otro."
} else {
  $env:PYTHONIOENCODING = "utf-8"
  $argv = @("-m", "eim.operation", "run", "--execution", "paper", "--port", "$Puerto",
            "--data-dir", "`"$DataDir`"")
  Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "vigilante.out.log") `
    -RedirectStandardError (Join-Path $logs "vigilante.err.log")
  Write-Host "Vigilante lanzado: API en http://127.0.0.1:$Puerto (operación en papel + bróker simulado)."
}

if ($ConWeb) {
  if (Escuchando 5173) {
    Write-Host "La interfaz ya está en http://127.0.0.1:5173"
  } else {
    Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
      -WorkingDirectory (Join-Path $v2 "eim\web") -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logs "web.out.log") `
      -RedirectStandardError (Join-Path $logs "web.err.log")
    Write-Host "Interfaz en http://127.0.0.1:5173"
  }
}
Write-Host "Registros: $logs · latido del bróker: $(Join-Path $DataDir 'paper\heartbeat.json')"
