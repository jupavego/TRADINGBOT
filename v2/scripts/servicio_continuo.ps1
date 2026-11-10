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

  Arranque seguro (T125): si la carpeta de datos no tiene historial, el vigilante NO arranca (crearía
  bases vacías) y lo explica en vigilante.err.log; -DatosNuevos lo permite (instalación nueva a
  propósito). Antes de nada en un equipo nuevo: `python -m eim.continuity check`.

  Prioridades (T126): fija EIM_PRIORITY=on y cada servicio toma su nivel al arrancar
  (`eim/operation/priority.py`): los recolectores en vivo por encima de lo normal; la API, los
  líderes y los vigilantes por debajo de los programas del usuario; su mantenimiento y Ollama al
  fondo (Idle). Puede correr dos veces a la vez (tarea al encender + tarea al iniciar sesión): un
  cerrojo global hace que la segunda
  espere a la primera y solo complete lo que falte; desde la sesión 0 (sin escritorio) no lanza el
  icono de la bandeja, que llega con la tarea de inicio de sesión.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1 -ConWeb
#>
param(
  [switch]$ConWeb,
  [switch]$DatosNuevos,
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

# Dos lanzamientos a la vez (al encender y al iniciar sesión): el segundo espera aquí a que el
# primero termine de lanzar y luego solo completa lo que falte. Desde la sesión del usuario no se
# ve la línea de órdenes de los procesos de la sesión 0 (ni siempre se puede abrir este cerrojo si
# lo creó la tarea al encender): lo que de verdad impide duplicados es el cerrojo de instancia de
# cada servicio (vigilantes, recolectores, «equipo despierto») y los puertos; estas comprobaciones
# solo evitan lanzar procesos que se irían al instante.
$turno = $null
try {
  $turno = New-Object System.Threading.Mutex($false, "Global\EIM_servicio_continuo")
  try { [void]$turno.WaitOne([TimeSpan]::FromMinutes(5)) } catch [System.Threading.AbandonedMutexException] { }
} catch { Start-Sleep -Seconds 30 }   # sin acceso: la otra tarea está lanzando; se le da ventaja

# Una tarea que corre sin sesión iniciada puede no traer las variables del usuario: se copian las
# EIM_* que falten (identidad del equipo, tope de DuckDB, ruta de Ollama...).
$delUsuario = [Environment]::GetEnvironmentVariables("User")
foreach ($k in @($delUsuario.Keys)) {
  if ($k -like "EIM_*" -and -not [Environment]::GetEnvironmentVariable($k, "Process")) {
    [Environment]::SetEnvironmentVariable($k, $delUsuario[$k], "Process")
  }
}
# T126: cada servicio fija su nivel de prioridad al arrancar (lo heredan todos los hijos).
if (-not $env:EIM_PRIORITY) { $env:EIM_PRIORITY = "on" }

function Escuchando([int]$p) {
  [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

# T126: ¿corre ya el servicio dueño de este cerrojo de instancia? Cada servicio bloquea el byte 0 de
# su archivo `*.lock` (`instance_lock`); el bloqueo lo ve cualquier sesión de Windows, al contrario
# que la línea de órdenes de los procesos de la sesión 0 (tarea al encender). Si está ocupado no se
# lanza nada: ni un duplicado que se iría al instante ni un Start-Process sobre su registro abierto.
function Ocupado([string]$cerrojo) {
  if (-not (Test-Path $cerrojo)) { return $false }
  try { $f = [System.IO.File]::Open($cerrojo, "Open", "ReadWrite", "ReadWrite") } catch { return $true }
  try { $f.Lock(0, 1); $f.Unlock(0, 1); return $false } catch { return $true } finally { $f.Close() }
}

# T140: Start-Process reescribe el registro que redirige, y así se perdió la evidencia de cuántas
# veces y desde cuándo se había quedado la API sin puerto. Se aparta el anterior con la hora de su
# última escritura y se guardan los $guardar más recientes. Nunca impide lanzar el servicio.
function Conservar([string]$ruta, [int]$guardar = 10) {
  try {
    if (-not (Test-Path -LiteralPath $ruta) -or (Get-Item -LiteralPath $ruta).Length -eq 0) { return }
    $dir = Split-Path -Parent $ruta
    $base = [IO.Path]::GetFileNameWithoutExtension($ruta)
    $sello = (Get-Item -LiteralPath $ruta).LastWriteTimeUtc.ToString("yyyyMMdd-HHmmss")
    Move-Item -LiteralPath $ruta (Join-Path $dir "$base.$sello.log") -Force
    Get-ChildItem -LiteralPath $dir -Filter "$base.*.log" | Sort-Object Name -Descending |
      Select-Object -Skip $guardar | Remove-Item -Force
  } catch { Write-Warning "no se pudo conservar $ruta : $_" }
}

# LLM local para el agente `context` (Ollama, solo en 127.0.0.1): se arranca si está instalado y no
# corre ya; el agente lo usa en segundo plano (no bloquea el ciclo) y sin él dice «sin datos».
$ollama = if ($env:EIM_OLLAMA_EXE) { $env:EIM_OLLAMA_EXE } else { "E:\Ollama\ollama.exe" }
if (Test-Path $ollama) {
  if (Escuchando 11434) {
    Write-Host "Ollama ya corre en 127.0.0.1:11434: no se lanza otro."
  } else {
    # T63 (BACKLOG T62 (1)): sin nube y solo en el bucle local; lo hereda el proceso lanzado
    $env:OLLAMA_NO_CLOUD = "1"
    $env:OLLAMA_HOST = "127.0.0.1:11434"
    $p = Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $logs "ollama.out.log") `
      -RedirectStandardError (Join-Path $logs "ollama.err.log")
    # T126: generar texto es trabajo de lote; sus procesos «runner» heredan Idle
    try { $p.PriorityClass = "Idle" } catch { }
    Write-Host "Ollama lanzado (LLM local de Contexto; tarda ~1 min en responder la primera vez)."
  }
  $env:EIM_CONTEXT_LLM = "local"   # lo heredan el vigilante y la API que lanza este script
} elseif ($env:EIM_OLLAMA_EXE) {
  # T128: configurado pero sin acceso (p. ej. una unidad de red, que la tarea al encender no ve).
  # La API lo avisa en sus alertas («LLM local no disponible») y en el motivo de Contexto.
  Write-Warning "EIM_OLLAMA_EXE apunta a $ollama, que no existe en esta sesión: Contexto queda sin datos."
} else {
  Write-Host "Ollama no está instalado ($ollama): Contexto queda en «sin datos» salvo ANTHROPIC_API_KEY."
}

# Los avisos salen por el icono de la bandeja (`icono_bandeja.ps1`), que lee los registros
# JSONL. Sin esto, `eim/operation/notify.py` lanza un PowerShell por aviso y el globo sale
# rotulado "Windows PowerShell", que es de donde cuelga su NotifyIcon de usar y tirar.
if (-not $env:EIM_NOTIFY) { $env:EIM_NOTIFY = "0" }

$vigOp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match '-m\s+eim\.operation\s+run(\s|$)' })
if (Escuchando $Puerto) {
  Write-Host "Ya hay un servicio en el puerto ${Puerto}: no se lanza otro."
} elseif ($vigOp -or (Ocupado (Join-Path $DataDir "operation\supervisor.lock"))) {
  Write-Host "El vigilante de la API ya corre y aún arranca: no se lanza otro."
} else {
  $argv = @("-m", "eim.operation", "run", "--execution", "paper", "--port", "$Puerto",
            "--data-dir", "`"$DataDir`"")
  if ($DatosNuevos) { $argv += "--allow-empty-data" }
  Conservar (Join-Path $logs "vigilante.out.log")
  Conservar (Join-Path $logs "vigilante.err.log")
  Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "vigilante.out.log") `
    -RedirectStandardError (Join-Path $logs "vigilante.err.log")
  Write-Host "Vigilante lanzado: API en http://127.0.0.1:$Puerto (operación en papel + bróker simulado)."
}

# Líderes (T41): sin puerto que mirar; se busca el proceso por su línea de órdenes. El cerrojo
# data/leaders/supervisor.lock impide de todos modos un segundo vigilante.
$lideres = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match '-m\s+eim\.leaders\s.*\s(supervise|run)(\s|$)' })
if ($lideres -or (Ocupado (Join-Path $DataDir "leaders\supervisor.lock"))) {
  Write-Host "El servicio de líderes ya corre: no se lanza otro."
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

# Microestructura (T23/T104): trades y libro de Binance → agente `microstructure`. Un vigilante por
# activo en foco (solo BTCUSDT desde T122; `eim.data.collectors.supervise`, cerrojo
# data\micro\supervisor[_SIMBOLO].lock) que relanza el recolector si cae o si su latido
# (data\micro\heartbeat[_SIMBOLO].json) se detiene, avisa si el disco o el flujo fallan y poda la
# profundidad vieja. Sin esto la esfera queda en «recolector apagado». Logs: micro.* (BTC) y
# micro_<SIMBOLO>.* (resto). ETHUSDT salió del foco el 2026-10-22 (T122): ya no se lanzan sus
# recolectores; los que sigan vivos de una sesión anterior se detienen a mano o al reiniciar.
# T128: donde hay captura HFT (BTCUSDT), la microestructura del agente sale de ella
# (`micro_feed`): fotos top-10 en data\micro\top y el mismo latido. El recolector T23 ya no se
# lanza para esos activos; uno que siga vivo de antes se para con detener_servicio.ps1 -Todo.
$activos = @("BTCUSDT")
$conHft = @("BTCUSDT")
$procs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue)
foreach ($a in $activos) {
  if ($conHft -contains $a) {
    Write-Host "Microestructura de ${a}: la deriva la captura HFT (T128); el recolector T23 no se lanza."
    continue
  }
  $sufijo = if ($a -eq "BTCUSDT") { "" } else { "_$a" }
  $vigMicro = @($procs | Where-Object { $_.CommandLine -match "eim\.data\.collectors\.supervise\s+$a" })
  $recMicro = @($procs | Where-Object { $_.CommandLine -match "eim\.data\.collectors\.binance_ws\s+$a" })
  if ($vigMicro -or (Ocupado (Join-Path $DataDir "micro\supervisor$sufijo.lock"))) {
    Write-Host "El vigilante de microestructura de $a ya corre: no se lanza otro."
  } elseif ($recMicro) {
    Write-Host "Hay un recolector de microestructura de $a SIN vigilante (PID $($recMicro.ProcessId -join ', ')): detenlo para que el vigilante lo relance con latido."
  } else {
    $argv = @("-m", "eim.data.collectors.supervise", $a, "--root", "`"$DataDir`"")
    Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logs "micro$sufijo.out.log") `
      -RedirectStandardError (Join-Path $logs "micro$sufijo.err.log") | Out-Null
    Write-Host "Vigilante de microestructura de $a lanzado (data\micro; 24 velas de acumulación antes de opinar)."
  }
}

# Captura HFT (T78): libro L2 completo con doble reloj, bookTicker, aggTrade, markPrice y
# liquidaciones de BTCUSDT en data\micro_hft, y la microestructura del agente (T128). Su vigilante
# (`eim.data.collectors.hft_supervise`, cerrojo data\micro_hft\supervisor.lock, latido
# data\micro_hft\heartbeat.json) relanza la captura si cae y cada 10 min audita la calidad de las
# horas cerradas, compacta y poda los crudos de más de 45 días. Logs: hft.out.log / hft.err.log.
$vigHft = @($procs | Where-Object { $_.CommandLine -match "eim\.data\.collectors\.hft_supervise\s+BTCUSDT" })
$recHft = @($procs | Where-Object { $_.CommandLine -match "eim\.data\.collectors\.hft_ws\s+BTCUSDT" })
if ($vigHft -or (Ocupado (Join-Path $DataDir "micro_hft\supervisor.lock"))) {
  Write-Host "El vigilante de la captura HFT ya corre: no se lanza otro."
} elseif ($recHft) {
  Write-Host "Hay una captura HFT SIN vigilante (PID $($recHft.ProcessId -join ', ')): detenla para que el vigilante la relance con latido."
} else {
  $argv = @("-m", "eim.data.collectors.hft_supervise", "BTCUSDT", "--root", "`"$DataDir`"")
  Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "hft.out.log") `
    -RedirectStandardError (Join-Path $logs "hft.err.log") | Out-Null
  Write-Host "Vigilante de la captura HFT lanzado (data\micro_hft; QC por hora en data\micro_hft\qc)."
}

# Liquidaciones en vivo (Binance/Bybit/OKX): alimentan al agente `liquidations`. Sin puerto: se
# busca por línea de órdenes para no duplicar. Uno por activo en foco.
foreach ($a in $activos) {
  $sufijo = if ($a -eq "BTCUSDT") { "" } else { "_$a" }
  $liq = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "eim\.data\.collectors\.liq_ws\s+$a" })
  if ($liq -or (Ocupado (Join-Path $DataDir "micro\liq_collector$sufijo.lock"))) {
    Write-Host "El recolector de liquidaciones de $a ya corre: no se lanza otro."
  } else {
    $argv = @("-m", "eim.data.collectors.liq_ws", $a, "--root", "`"$DataDir`"")
    Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $v2 -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logs "liq$sufijo.out.log") `
      -RedirectStandardError (Join-Path $logs "liq$sufijo.err.log") | Out-Null
    Write-Host "Recolector de liquidaciones de $a lanzado (data\micro\liqs; ~24 velas de acumulación antes de opinar)."
  }
}

# Vigilancia de video (T64, opcional): solo con EIM_VIDEO=1. Una pasada por hora a la YouTube
# Data API v3 (solo metadatos; necesita EIM_YOUTUBE_API_KEY), catálogo en data\video.duckdb y
# latido en data\video\heartbeat.json. Cerrojo data\video\service.lock: no se duplica.
if ($env:EIM_VIDEO -eq "1") {
  if (Ocupado (Join-Path $DataDir "video\service.lock")) {
    Write-Host "El servicio de video ya corre: no se lanza otro."
  } else {
    Start-Process -FilePath $py -ArgumentList @("-m", "eim.video", "--data-dir", "`"$DataDir`"", "run") `
      -WorkingDirectory $v2 -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logs "video.out.log") `
      -RedirectStandardError (Join-Path $logs "video.err.log") | Out-Null
    Write-Host "Servicio de video lanzado (data\video.duckdb; latido en data\video)."
  }
}

# Registro de consumo (T127): CPU, RAM y prioridad de cada proceso del EIM y del equipo cada
# 30 s en data\usage\ (sin abrir los procesos: también ve los de la sesión 0).
if (Ocupado (Join-Path $DataDir "usage\usage.lock")) {
  Write-Host "El registro de consumo ya corre: no se lanza otro."
} else {
  Start-Process -FilePath $py -ArgumentList @("-m", "eim.operation.usage", "run", "--data-dir", "`"$DataDir`"") `
    -WorkingDirectory $v2 -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "consumo.out.log") `
    -RedirectStandardError (Join-Path $logs "consumo.err.log") | Out-Null
  Write-Host "Registro de consumo lanzado (data\usage)."
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
  $vite = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'eim[\\/]web.*vite' })
  if ((Escuchando 5173) -or $vite) {   # Vite que aún arranca: otro tomaría el puerto 5174
    Write-Host "La interfaz ya está en http://127.0.0.1:5173"
  } else {
    Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
      -WorkingDirectory (Join-Path $v2 "eim\web") -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logs "web.out.log") `
      -RedirectStandardError (Join-Path $logs "web.err.log")
    Write-Host "Interfaz en http://127.0.0.1:5173"
  }
}
# Icono junto al reloj: estado del servicio y avisos. Va aqui y no en `abrir_interfaz.ps1`
# para que tambien aparezca cuando el servicio arranca solo con Windows (tarea programada).
# Si ya hay uno, el propio script se va (mutex), asi que repetir no duplica. En la sesion 0
# (tarea al encender, sin escritorio) no se veria: lo lanza la tarea de inicio de sesion.
if ((Get-Process -Id $PID).SessionId -ne 0) {
  Start-Process "wscript.exe" -ArgumentList @(
    ("`"" + (Join-Path $PSScriptRoot "eim_oculto.vbs") + "`""),
    ("`"" + (Join-Path $PSScriptRoot "icono_bandeja.ps1") + "`"")) -WindowStyle Hidden
}

# T120: arranque comprobable. Lo que ya corría se adopta solo si corre desde ESTA carpeta; si un
# latido dice otro checkout (un worktree, una copia vieja) se avisa claro y no se lanza encima un
# duplicado. Los que acaban de lanzarse tardan ~1 min en dar su primer latido.
Push-Location $v2
try { & $py -m eim.operation.components --data-dir "$DataDir" --expect "$v2" } finally { Pop-Location }
if ($LASTEXITCODE -eq 3) {
  Write-Warning "Hay servicios corriendo desde otra carpeta (ver AVISO arriba): esta carpeta no los adopta. Detenlos con detener_servicio.ps1 -Todo y vuelve a lanzar este script."
}

Write-Host "Registros: $logs · latido del bróker: $(Join-Path $DataDir 'paper\heartbeat.json') · latido de líderes: $(Join-Path $DataDir 'leaders\heartbeat.json')"
try { $turno.ReleaseMutex() } catch { }
