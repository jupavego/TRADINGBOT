<#
.SYNOPSIS
  Deja corriendo sin parar el servicio del EIM (T48): vigilante -> API + operación en papel +
  bróker simulado (15 m, 1 h y 4 h), y el servicio de líderes de copy trading (T41). Con -ConWeb
  también la interfaz en http://127.0.0.1:5173. Además mantiene el equipo despierto
  (`mantener_despierto.ps1`) y sirve la hoja de ruta en http://127.0.0.1:8765/roadmap.html.

.DESCRIPTION
  El vigilante (`python -m eim.operation run --execution paper`) relanza la API si se cae o si su
  latido se detiene. Dentro de la API, el bróker simulado analiza cada vela cerrada y abre
  operaciones en papel; nunca envía órdenes reales. Si ya hay algo escuchando en el puerto, no se
  lanza otra copia (se puede ejecutar varias veces sin duplicar).
  Líderes: `python -m eim.leaders supervise` corre aparte (es el único proceso que puede abrir
  data/leaders.duckdb) y relanza la captura de Hyperliquid si cae o si su latido
  (data/leaders/heartbeat.json) se detiene; escribe el tablero cada 5 min. Si ya corre (o hay un
  `run` a mano), no se lanza otro. Solo lectura de datos públicos.

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
$env:PYTHONIOENCODING = "utf-8"

function Escuchando([int]$p) {
  [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

if (Escuchando $Puerto) {
  Write-Host "Ya hay un servicio en el puerto ${Puerto}: no se lanza otro."
} else {
  $argv = @("-m", "eim.operation", "run", "--execution", "paper", "--port", "$Puerto",
            "--data-dir", "`"$DataDir`"")
  Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "vigilante.out.log") `
    -RedirectStandardError (Join-Path $logs "vigilante.err.log")
  Write-Host "Vigilante lanzado: API en http://127.0.0.1:$Puerto (operación en papel + bróker simulado)."
}

# Líderes (T41): sin puerto que mirar; se busca el proceso por su línea de órdenes. El cerrojo
# data/leaders/supervisor.lock impide de todos modos un segundo vigilante.
$lideres = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match '-m\s+eim\.leaders\s.*\s(supervise|run)(\s|$)' })
if ($lideres) {
  Write-Host "El servicio de líderes ya corre (PID $($lideres.ProcessId -join ', ')): no se lanza otro."
} else {
  $argv = @("-m", "eim.leaders", "--root", "`"$DataDir`"", "supervise")
  $out = Join-Path $logs "lideres.out.log"
  $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError (Join-Path $logs "lideres.err.log") -PassThru
  if ($p.WaitForExit(10000)) {   # sale enseguida si no hay líderes en seguimiento o la base está en uso
    Write-Host "Servicio de líderes NO lanzado: $(Get-Content $out -Tail 1 -Encoding UTF8)"
  } else {
    Write-Host "Servicio de líderes lanzado (captura de Hyperliquid, tablero cada 5 min en data\leaders)."
  }
}

# Liquidaciones en vivo (Binance/Bybit/OKX): alimentan al agente `liquidations`. Sin puerto: se
# busca por línea de órdenes para no duplicar. BTCUSDT por defecto (foco actual).
$liq = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'eim\.data\.collectors\.liq_ws' })
if ($liq) {
  Write-Host "El recolector de liquidaciones ya corre (PID $($liq.ProcessId -join ', ')): no se lanza otro."
} else {
  $argv = @("-m", "eim.data.collectors.liq_ws", "BTCUSDT", "--root", "`"$DataDir`"")
  Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "liq.out.log") `
    -RedirectStandardError (Join-Path $logs "liq.err.log") | Out-Null
  Write-Host "Recolector de liquidaciones lanzado (data\micro\liqs; ~24 velas de acumulación antes de opinar)."
}

# Equipo despierto: proceso aparte que pide a Windows no suspender por inactividad mientras la
# API esté arriba (no toca el plan de energía; ver mantener_despierto.ps1). No se duplica.
$despierto = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'mantener_despierto\.ps1' })
if ($despierto) {
  Write-Host "El modo «equipo despierto» ya está activo (PID $($despierto.ProcessId -join ', '))."
} else {
  $guion = Join-Path $PSScriptRoot "mantener_despierto.ps1"
  Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$guion`"", "-Puerto", "$Puerto")
  Write-Host "Modo «equipo despierto» activado: Windows no se suspenderá por inactividad mientras la API corra."
}

# Hoja de ruta en http://127.0.0.1:8765 (estática, solo lectura). Sirve la carpeta VIVA
# `data\roadmap_live`, que `python PLAN/build_roadmap.py` actualiza desde cualquier worktree:
# el icono del escritorio muestra siempre el avance más reciente, sin servidores nuevos por tarea.
$vivo = Join-Path $v2 "data\roadmap_live"
$plan = Join-Path (Split-Path -Parent $v2) "PLAN"
New-Item -ItemType Directory -Force $vivo | Out-Null
if (-not (Test-Path (Join-Path $vivo "roadmap.html"))) {
  foreach ($f in "roadmap.html", "status.js") { Copy-Item (Join-Path $plan $f) $vivo -ErrorAction SilentlyContinue }
}
if (Escuchando 8765) {
  Write-Host "La hoja de ruta ya está en http://127.0.0.1:8765/roadmap.html"
} else {
  Start-Process -FilePath $py -ArgumentList @("-m", "http.server", "8765", "--bind", "127.0.0.1",
    "--directory", "`"$vivo`"") -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "roadmap.out.log") `
    -RedirectStandardError (Join-Path $logs "roadmap.err.log")
  Write-Host "Hoja de ruta en http://127.0.0.1:8765/roadmap.html"
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
Write-Host "Registros: $logs · latido del bróker: $(Join-Path $DataDir 'paper\heartbeat.json') · latido de líderes: $(Join-Path $DataDir 'leaders\heartbeat.json')"
