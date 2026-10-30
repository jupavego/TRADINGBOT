<#
.SYNOPSIS
  Registra (o quita con -Quitar) la tarea de Windows «EIM - copia externa diaria» (T125): cada día
  a las 20:30 hora local (después de la copia diaria del servicio, a las 00:00 UTC) ejecuta
  `copia_externa.ps1`, que sube la copia completa verificada al repo privado de datos y publica
  la experiencia de este equipo. Si el equipo estaba apagado, corre al volver
  (`StartWhenAvailable`). Solo para el usuario actual; no requiere administrador.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_copia_externa.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_copia_externa.ps1 -Quitar
#>
param([switch]$Quitar, [string]$Hora = "20:30")
$ErrorActionPreference = "Stop"
$nombre = "EIM - copia externa diaria"

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $nombre -Confirm:$false
  Write-Host "Tarea quitada: $nombre"
  return
}

$script = Join-Path $PSScriptRoot "copia_externa.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$disparo = New-ScheduledTaskTrigger -Daily -At $Hora
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparo -Settings $ajustes `
  -Description "EIM T125: copia completa verificada al repo privado de datos (GitHub) y exportación de la experiencia de este equipo. Registro en data\operation\logs\copia_externa.log." `
  -Force | Out-Null
Write-Host "Tarea registrada: '$nombre' (cada día a las $Hora). Probarla ahora: Start-ScheduledTask -TaskName '$nombre'"
