<#
.SYNOPSIS
  Registra (o quita con -Quitar) una tarea programada de Windows que ejecuta
  `servicio_continuo.ps1 -ConWeb` al iniciar sesión, para que el bróker simulado (T48) y la
  captura de líderes de copy trading (T41) sigan después de reiniciar el equipo. Solo para el
  usuario actual; no requiere administrador. La tarea ejecuta el script por su ruta: lo que se
  añada a `servicio_continuo.ps1` entra sin reinstalarla (reinstalar solo actualiza la descripción).
  El nombre de la tarea no cambia para no dejar una copia vieja registrada.

.DESCRIPTION
  -AlEncender (T126) registra además una segunda tarea, «EIM - servicio continuo al encender»,
  que lanza los mismos servicios 2 min después de arrancar Windows SIN esperar a que alguien
  inicie sesión: tras un corte o un reinicio la captura no queda parada horas en la pantalla de
  entrada (el 2026-10-31 se perdieron así ~23 h). Corre con el usuario actual en modo S4U (sin
  guardar contraseña): solo recursos locales e internet público; sin unidades de red (Z:) ni el
  almacén de credenciales, por eso la copia externa sigue en su propia tarea interactiva. Exige
  una consola de administrador. La tarea de inicio de sesión se conserva: al entrar, completa lo
  que falte y pone el icono de la bandeja (el script espera a la otra y no duplica nada).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -Quitar
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -AlEncender
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -AlEncender -Quitar
#>
param([switch]$Quitar, [switch]$AlEncender)
$ErrorActionPreference = "Stop"
$nombre = "EIM - servicio continuo (broker simulado)"
$nombreEncender = "EIM - servicio continuo al encender"
if ($AlEncender) { $nombre = $nombreEncender }

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $nombre -Confirm:$false
  Write-Host "Tarea quitada: $nombre"
  return
}

$script = Join-Path $PSScriptRoot "servicio_continuo.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -ConWeb"
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

if ($AlEncender) {
  $yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not $yo.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Hace falta una consola de PowerShell abierta como administrador para registrar '$nombre'."
    exit 1
  }
  $disparo = New-ScheduledTaskTrigger -AtStartup
  $disparo.Delay = "PT2M"   # red y disco listos antes de abrir los WebSocket
  $quien = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U `
    -RunLevel Limited
  Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparo -Principal $quien `
    -Settings $ajustes -Force `
    -Description "Lanza los servicios del EIM al encender el equipo, sin esperar al inicio de sesión (T126)." |
    Out-Null
  Write-Host "Tarea registrada: '$nombre' (2 min después de encender, sin iniciar sesión)."
  return
}

$disparo = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparo -Settings $ajustes `
  -Description "Lanza el vigilante del EIM (API + operación en papel + bróker simulado) y el servicio de líderes de copy trading al iniciar sesión." `
  -Force | Out-Null
Write-Host "Tarea registrada: '$nombre' (al iniciar sesión). Ejecuta ahora: $script -ConWeb"
