<#
.SYNOPSIS
  Abre la interfaz del EIM con un doble clic (lo usa el acceso directo del escritorio que crea
  `crear_acceso_escritorio.ps1`). Asegura el servicio completo con
  `servicio_continuo.ps1 -ConWeb` (vigilante, API en papel, bróker simulado, líderes, interfaz,
  hoja de ruta y modo «equipo despierto»; no duplica lo que ya corre), espera a que respondan
  y abre http://127.0.0.1:5173 y la hoja de ruta en el navegador predeterminado. Si algo no arranca a tiempo, la ventana
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
  $txt = "$motivo`n`nRegistros: $logs (vigilante.*.log, web.*.log).`nIncidentes: v2\docs\RUNBOOK.md"
  Write-Host $txt -ForegroundColor Red
  # Se lanza sin consola (eim_oculto.vbs), asi que el aviso tiene que ser una ventana.
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show($txt, "EIM - no se pudo abrir", "OK", "Error") | Out-Null
  exit 1
}

Write-Host "Asegurando el servicio del EIM (vigilante + API en papel + bróker + líderes + interfaz + equipo despierto)..."
try { & (Join-Path $PSScriptRoot "servicio_continuo.ps1") -ConWeb } catch { Falla "No se pudo lanzar el servicio: $_" }
# El icono junto al reloj sustituye a la consola: aparece apagado y se enciende al responder.
Start-Process wscript.exe -ArgumentList @(
  ("`"" + (Join-Path $PSScriptRoot "eim_oculto.vbs") + "`""),
  ("`"" + (Join-Path $PSScriptRoot "icono_bandeja.ps1") + "`""))

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
Write-Host "Abriendo $web y la hoja de ruta"
Start-Process $web
Start-Process "http://127.0.0.1:8765/roadmap.html"
