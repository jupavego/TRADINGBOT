<#
.SYNOPSIS
  Escaner global diario (T95, decision del usuario 2026-11-26): pone al dia el catalogo y las
  velas del universo, hace un barrido y la pasada de agentes con el ranking, los grupos y el
  registro de intentos. Modo ANALISIS: no envia ordenes ni toca T31, la cantera ni la API.

.DESCRIPTION
  Corre a diario a las 00:45 UTC (19:45 en Bogota), cuando ya cerro la vela diaria, con
  prioridad baja (`eim.operation.priority run batch`). Es idempotente: repetirla el mismo dia
  no duplica intentos (una observacion por intento y vela), y si el equipo estaba apagado la
  tarea arranca en cuanto se enciende (StartWhenAvailable).

  Vigia propio: al terminar comprueba que la vista del escaner se publico en las ultimas 6 horas
  con el ranking de T95; si no, espera 20 minutos y lo intenta una vez mas. Cada pasada deja una
  linea en data\operation\logs\escaner_diario.log (bien o FALLO); los fallos del codigo van
  ademas al Observatorio (servicio del escaner). La revision del 2026-12-29 cuenta los dias que
  corrio. Si ya hay un `python -m eim.scanner run` en marcha, no hace nada (lo hace el servicio).

  T102: al final, pase lo que pase, la revision de salud multiactivo (`python -m eim.scanner
  health`): salud por clase y por fuente, despliegue gradual, avisos locales y eventos por lotes al
  Observatorio. Su linea va al mismo registro ("salud (codigo N): ..."). Si la pasada fallo, la
  revision lo ve: con la vista vieja acaba en "obsoleto" y avisa.

  -Instalar registra la tarea diaria; -Quitar la borra. Instalar SOLO en la laptop (es donde
  viven el universo y scanner.duckdb).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\escaner_diario.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\escaner_diario.ps1 -Instalar
#>
param([switch]$Instalar, [switch]$Quitar)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - escaner diario (T95)"
$registro = Join-Path $datos "operation\logs\escaner_diario.log"
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
  # 00:45 UTC: la vela diaria cierra a las 00:00 UTC; antes de la cantera (01:30) y la apertura (02:10).
  $utc = [DateTime]::SpecifyKind([DateTime]"2026-11-27T00:45:00", [DateTimeKind]::Utc)
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"")
  $cuando = New-ScheduledTaskTrigger -Daily -At $utc.ToLocalTime()
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes -Force | Out-Null
  Write-Host "Tarea registrada: $tarea (a diario $($utc.ToLocalTime().ToString('HH:mm')) hora local)"
  exit 0
}

function Corre([string[]]$orden) {
  $ErrorActionPreference = "Continue"   # avisos por stderr de Python no son un fallo
  $salida = & $py -m eim.operation.priority run batch -- $py -m eim.scanner --data-dir $datos @orden 2>&1
  return @{ codigo = $LASTEXITCODE; texto = (($salida | Out-String).Trim() -replace "\s+", " ") }
}

function Pasada {
  $s = Corre @("sync", "--discover")
  if ($s.codigo -ne 0) { return "sync codigo $($s.codigo): $($s.texto)" }
  $r = Corre @("run", "--once", "--no-quotes", "--no-sync")
  if ($r.codigo -eq 2) { return "ya-en-marcha" }
  if ($r.codigo -ne 0) { return "run codigo $($r.codigo): $($r.texto)" }
  $ErrorActionPreference = "Continue"
  $vista = Join-Path $datos "scanner\view.json"
  $chk = & $py -c "import json,sys,time; v=json.load(open(sys.argv[1],encoding='utf-8')); r=v.get('ranking') or {}; f=r.get('family') or {}; age=(time.time()*1000-v.get('generated_at',0))/3600000; print('ok' if age<6 and r.get('available') else 'vista vieja o sin ranking: %.1f h, %s' % (age, r.get('error') or r.get('reason') or ''), f.get('total'), f.get('new_observations'), f.get('matured'), r.get('n_above'))" $vista
  if (-not ($chk -like "ok*")) { return "vigia: $chk" }
  return "bien: $chk"
}

function Salud {
  # T102: revision de salud multiactivo; nunca hace fallar la tarea por si misma
  $ErrorActionPreference = "Continue"
  $f = Join-Path $datos "scanner\salud_ultima.txt"
  if (Test-Path $f) { Remove-Item -Force $f }
  & $py -m eim.operation.priority run batch -- $py -m eim.scanner --data-dir $datos health --summary $f 2>&1 | Out-Null
  $c = $LASTEXITCODE
  $t = if (Test-Path $f) { (Get-Content -Raw -Encoding UTF8 $f).Trim() } else { "sin resumen" }
  Anota "salud (codigo $c): $t"
}

try {
  Push-Location $v2
  $res = Pasada
  if (-not ($res -like "bien:*") -and $res -ne "ya-en-marcha") {
    Anota "reintento en 20 min tras: $res"
    Start-Sleep -Seconds 1200
    $res = Pasada
  }
  Salud
  Pop-Location
  if ($res -eq "ya-en-marcha") { Anota "bien: el servicio del escaner ya estaba en marcha"; exit 0 }
  if (-not ($res -like "bien:*")) { throw $res }
  Anota "$res (familia, observaciones nuevas, maduras, sobre el umbral)"
} catch {
  Anota "FALLO: $_"
  exit 1
}
