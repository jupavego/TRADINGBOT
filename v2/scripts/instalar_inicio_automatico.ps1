<#
.SYNOPSIS
  Registra (o quita con -Quitar) una tarea programada de Windows que ejecuta
  `servicio_continuo.ps1 -ConWeb` al iniciar sesión, para que el bróker simulado siga operando
  después de reiniciar el equipo (T48). Solo para el usuario actual; no requiere administrador.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -Quitar
#>
param([switch]$Quitar)
$ErrorActionPreference = "Stop"
$nombre = "EIM - servicio continuo (broker simulado)"

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $nombre -Confirm:$false
  Write-Host "Tarea quitada: $nombre"
  return
}

$script = Join-Path $PSScriptRoot "servicio_continuo.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -ConWeb"
$disparo = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparo -Settings $ajustes `
  -Description "Lanza el vigilante del EIM (API + operación en papel + bróker simulado) al iniciar sesión." `
  -Force | Out-Null
Write-Host "Tarea registrada: '$nombre' (al iniciar sesión). Ejecuta ahora: $script -ConWeb"
