<#
.SYNOPSIS
  Colector de las cadenas de opciones de Deribit (T213): cada N horas guarda una toma del libro de
  todas las opciones vivas de BTC en data\options\. No arranca ningun servicio nuevo ni toca los
  que ya corren.

  Fuente aprobada por el usuario a nivel 1 (PLAN\notas\T213_terminos.md): solo uso personal, nada
  se publica ni se reenvia. Solo informacion sobre la volatilidad: no se operan opciones.

.DESCRIPTION
  Ejecuta `python -m eim.data.options_chain snapshot` con prioridad de lote (IDLE,
  `eim.operation.priority`), para no competir con la captura HFT ni con el broker simulado. Cada
  pasada es UNA llamada publica por moneda; si la hora ya tiene toma, no la repite.

  Las tomas quedan en `data\options\<MONEDA>\<dia>\<HH>.jsonl.gz` (+ `<HH>.quality.json`, calidad
  por vencimiento) y entran en la copia diaria. Cada pasada deja una linea en
  `data\operation\logs\opciones.log`, tambien si falla.

  Cadencia y monedas: las fijo aplicar_t213 tras MEDIR el volumen de una toma real
  (`python -m eim.data.options_chain measure`) contra el presupuesto declarado de 1 MB/dia; si no
  cabe se reduce la frecuencia, nunca los campos. Las tomas caen en horas UTC multiplo de
  -CadaHoras (siempre incluye las 00:00 UTC, la lectura que importa en T165), al minuto 1.

  -Instalar registra la tarea; -Quitar la borra. Instalala desde la carpeta principal del equipo
  que la vaya a correr (la que corre los servicios), no desde un worktree.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\opciones_colector.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\opciones_colector.ps1 -Instalar -CadaHoras 1
  powershell -ExecutionPolicy Bypass -File v2\scripts\opciones_colector.ps1 -Quitar
#>
param([switch]$Instalar, [switch]$Quitar, [string]$Monedas = "BTC", [int]$CadaHoras = 1)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
$datos = Join-Path $v2 "data"
$tarea = "EIM - colector de opciones de Deribit (T213)"
$registro = Join-Path $datos "operation\logs\opciones.log"

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
  if (@(1, 2, 3, 4, 6, 8, 12, 24) -notcontains $CadaHoras) { throw "CadaHoras debe dividir 24" }
  # Primera toma: la proxima hora UTC multiplo de CadaHoras, al minuto 1, en hora local.
  $utc = (Get-Date).ToUniversalTime()
  $primera = $utc.Date.AddHours($utc.Hour).AddMinutes(1)
  while ($primera -le $utc -or ($primera.Hour % $CadaHoras) -ne 0) { $primera = $primera.AddHours(1) }
  $primera = $primera.ToLocalTime()
  $accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $v2 -Argument (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" " +
    "-Monedas $Monedas")
  $cuando = New-ScheduledTaskTrigger -Once -At $primera `
    -RepetitionInterval (New-TimeSpan -Hours $CadaHoras)
  $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $cuando -Settings $ajustes `
    -Description ("EIM T213: guarda una toma de la cadena de opciones de Deribit (publica, sin " +
      "clave, uso personal) en data\options\ cada $CadaHoras h. Prioridad de lote. Registro en " +
      "data\operation\logs\opciones.log.") `
    -Force | Out-Null
  Write-Host "Tarea registrada: '$tarea' (cada $CadaHoras h, monedas $Monedas, primera a las $primera)."
  Write-Host "Probarla ahora: Start-ScheduledTask -TaskName '$tarea'"
  exit 0
}

try {
  if (-not (Test-Path $py)) {
    throw "no existe ${py}; este script corre desde la carpeta principal, no desde un worktree"
  }
  $salida = & $py -m eim.operation.priority run batch -- `
    $py -m eim.data.options_chain snapshot --data $datos --currency $Monedas 2>&1
  if ($LASTEXITCODE -ne 0) { throw "codigo $LASTEXITCODE : $($salida -join ' ')" }
  # Asignar antes de recorrer: en PowerShell 5.1 `ConvertFrom-Json` no desenrolla el arreglo.
  $filas = ConvertFrom-Json ($salida | Out-String)
  $resumen = ($filas | ForEach-Object {
    $c = $_
    if ($c.already) { "$($c.currency) ya tomada ($($c.taken_at))" } else { "$($c.currency) filas=$($c.rows) descartes=$($c.dropped) vencimientos=$($c.expiries) bytes=$($c.bytes) a=$($c.taken_at)" }
  }) -join " | "
  Anota "bien: $resumen"
  Write-Host $resumen
} catch {
  Anota "FALLO: $_"
  exit 1
}
