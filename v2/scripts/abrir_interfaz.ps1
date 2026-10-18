<#
.SYNOPSIS
  Abre la interfaz del EIM con un doble clic (lo usa el acceso directo del escritorio que crea
  `crear_acceso_escritorio.ps1`). Si la API o la web no responden, las arranca con
  `servicio_continuo.ps1 -ConWeb` (no duplica lo que ya corre), espera a que respondan y abre
  http://127.0.0.1:5173 en el navegador predeterminado. Si algo no arranca a tiempo, la ventana
  queda abierta con lo que falla y dónde están los registros.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\abrir_interfaz.ps1
#>
param([int]$Espera = 120)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Host.UI.RawUI.WindowTitle = "EIM - abriendo la interfaz"
$web = "http://127.0.0.1:5173"
$api = "http://127.0.0.1:8000/v2/health"

function Responde([string]$url) {
  try { (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $false }
}

function Falla([string]$motivo) {
  $logs = Join-Path (Split-Path -Parent $PSScriptRoot) "data\operation\logs"
  Write-Host ""
  Write-Host $motivo -ForegroundColor Red
  Write-Host "Registros: $logs (vigilante.*.log, web.*.log). Incidentes: v2\docs\RUNBOOK.md"
  Read-Host "Pulsa Enter para cerrar"
  exit 1
}

if (-not ((Responde $api) -and (Responde $web))) {
  Write-Host "Arrancando el servicio del EIM (API en papel + interfaz)..."
  try { & (Join-Path $PSScriptRoot "servicio_continuo.ps1") -ConWeb } catch { Falla "No se pudo lanzar el servicio: $_" }
  Write-Host "Esperando a que respondan la API y la interfaz (hasta $Espera s)..."
  $limite = (Get-Date).AddSeconds($Espera)
  while (-not ((Responde $api) -and (Responde $web))) {
    if ((Get-Date) -gt $limite) {
      $caidos = @()
      if (-not (Responde $api)) { $caidos += "API ($api)" }
      if (-not (Responde $web)) { $caidos += "interfaz ($web)" }
      Falla "Sin respuesta tras $Espera s: $($caidos -join ', ')."
    }
    Start-Sleep -Seconds 1
  }
}
Write-Host "Abriendo $web"
Start-Process $web
