<#
.SYNOPSIS
  Evita que Windows se suspenda por inactividad mientras el servicio del EIM está en marcha.

.DESCRIPTION
  Pide al sistema, con `SetThreadExecutionState` (ES_CONTINUOUS | ES_SYSTEM_REQUIRED), que no entre
  en suspensión por inactividad. Es una petición de ESTE proceso: no cambia el plan de energía ni
  ningún ajuste de Windows, y se libera sola al terminar el proceso. La pantalla SÍ puede apagarse
  (no se pide ES_DISPLAY_REQUIRED). Vigila el puerto de la API: si deja de escuchar más de
  -GraciaSeg segundos, libera la petición y termina (el equipo vuelve a su comportamiento normal).
  No impide la suspensión manual (menú Inicio) ni al cerrar la tapa del portátil: eso lo decide
  Windows; en un portátil, ajustar «Al cerrar la tapa: No hacer nada» en Opciones de energía.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\mantener_despierto.ps1
#>
param([int]$Puerto = 8000, [int]$GraciaSeg = 180, [int]$CadaSeg = 30)
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "EIM - equipo despierto"

Add-Type -Namespace EIM -Name Energia -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint estado);
"@
[uint32]$CONTINUO = 2147483648          # ES_CONTINUOUS
[uint32]$SISTEMA = 1                    # ES_SYSTEM_REQUIRED

function Escuchando([int]$p) {
  [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

$caidaDesde = $null
Write-Host "EIM: el equipo no se suspenderá por inactividad mientras la API escuche en el puerto $Puerto."
try {
  while ($true) {
    # Se reafirma en cada vuelta (misma hebra): la petición es por hebra y caduca con ella.
    [void][EIM.Energia]::SetThreadExecutionState($CONTINUO -bor $SISTEMA)
    if (Escuchando $Puerto) { $caidaDesde = $null }
    elseif (-not $caidaDesde) { $caidaDesde = Get-Date }
    elseif (((Get-Date) - $caidaDesde).TotalSeconds -gt $GraciaSeg) {
      Write-Host "La API lleva más de $GraciaSeg s sin responder: se libera la petición de no suspender."
      break
    }
    Start-Sleep -Seconds $CadaSeg
  }
} finally {
  [void][EIM.Energia]::SetThreadExecutionState($CONTINUO)   # libera
}
