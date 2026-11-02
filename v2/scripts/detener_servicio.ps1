<#
.SYNOPSIS
  Para los servicios del EIM en cualquier sesión de Windows: primero los vigilantes, para que no
  relancen a sus hijos, y después los servicios (T127).

.DESCRIPTION
  Sin -Todo para lo mismo que «Parar servicio» del icono: la operación en papel (vigilante y API),
  los líderes, la interfaz y «equipo despierto». La captura (microestructura, HFT y liquidaciones),
  el registro de consumo y la hoja de ruta siguen. Con -Todo para también todo eso.

  No hace falta administrador: cada servicio Python del EIM da permiso a su usuario al arrancar
  (`eim/operation/proc_access.py`), también si lo lanzó la tarea al encender en la sesión 0. Al
  final lista lo que, en otra sesión, no se deja ver: servicios arrancados antes de T127, la
  interfaz (Vite), la hoja de ruta y «equipo despierto», que se va solo a los 3 min sin API. Para
  esos, reiniciar el equipo o usar una consola de administrador.

  -SoloCon <texto> limita a los procesos cuya línea de órdenes contiene ese texto (pruebas).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\detener_servicio.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\detener_servicio.ps1 -Todo
#>
param([switch]$Todo, [string]$SoloCon = "")
$ErrorActionPreference = "Continue"

$vigilantes = @('-m\s+eim\.operation\s+run(\s|$)', '-m\s+eim\.leaders\s.*\ssupervise(\s|$)')
$servicios = @('-m\s+uvicorn\s+eim\.api\.main:app', '-m\s+eim\.leaders\s.*\srun(\s|$)',
               'eim[\\/]web[\\/]node_modules[\\/]vite', 'mantener_despierto\.ps1')
if ($Todo) {
  $vigilantes += 'eim\.data\.collectors\.(hft_)?supervise\s'
  $servicios += @('eim\.data\.collectors\.(binance_ws|hft_ws|liq_ws)\s', '-m\s+eim\.operation\.usage\s',
                  '-m\s+http\.server\s+8765')
}

function Procesos([string[]]$patrones) {
  @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $c = $_.CommandLine
      $_.Name -match '^(python|pythonw|node|powershell)\.exe$' -and $c -and $_.ProcessId -ne $PID -and
      (-not $SoloCon -or $c.Contains($SoloCon)) -and
      ($patrones | Where-Object { $c -match $_ })
  })
}

function Parar([string]$que, [object[]]$lista) {
  foreach ($p in $lista) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  Write-Host ("{0}: {1}" -f $que, $(if ($lista) { ($lista.ProcessId -join ', ') } else { 'ninguno' }))
  if (-not $lista) { return 0 }
  Start-Sleep -Milliseconds 500
  $vivos = @($lista | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
  foreach ($p in $vivos) { Write-Host "  sin permiso para parar $($p.ProcessId) (sesión $($p.SessionId))" }
  return $vivos.Count
}

$fallos = Parar "Vigilantes" (Procesos $vigilantes)
Start-Sleep -Seconds 2
$fallos += Parar "Servicios" (Procesos ($vigilantes + $servicios))
Start-Sleep -Seconds 3
$quedan = Procesos ($vigilantes + $servicios)
if ($quedan) { $fallos += Parar "Reintento" $quedan }

if (-not $SoloCon) {
  $mia = (Get-Process -Id $PID).SessionId
  $ocultos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.SessionId -ne $mia -and $_.Name -match '^(python|pythonw|node)\.exe$' -and -not $_.CommandLine })
  if ($ocultos) {
    Write-Host (("En otra sesión quedan {0} procesos que no se dejan ver (PID {1}): servicios " +
                 "arrancados antes de T127, la interfaz o la hoja de ruta. Para ellos: reiniciar el " +
                 "equipo o una consola de administrador.") -f $ocultos.Count, ($ocultos.ProcessId -join ', '))
  }
}
exit $(if ($fallos) { 2 } else { 0 })
