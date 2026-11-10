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

  -Vigilante (T148) registra la tercera tarea, «EIM - vigilante del conjunto», que es la que
  faltaba: las otras dos solo saltan al encender y al iniciar sesión, así que con Windows ya
  encendido y la sesión abierta nadie vuelve a mirar. El 2026-11-09 los cinco servicios estuvieron
  parados 5 h 26 min por eso (`PLAN/notas/T148_apagon_2026-11-09.md`). Esta corre cada 5 min con
  disparador repetido, comprueba los cinco latidos y levanta los servicios de datos si falta
  alguno desde hace 10 min (`vigilante_conjunto.ps1` → `eim/operation/fleet_watch.py`: tope de
  intentos, espera creciente y aviso al usuario). Solo para el usuario actual, sin administrador;
  al registrarla se quita el parche provisional «EIM - vigilante del conjunto (T148)», que hacía
  lo mismo a ciegas y sin tope de intentos.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -Quitar
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -AlEncender
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -AlEncender -Quitar
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -Vigilante
  powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_inicio_automatico.ps1 -Vigilante -Quitar
#>
param([switch]$Quitar, [switch]$AlEncender, [switch]$Vigilante)
$ErrorActionPreference = "Stop"
$nombre = "EIM - servicio continuo (broker simulado)"
$nombreEncender = "EIM - servicio continuo al encender"
$nombreVigilante = "EIM - vigilante del conjunto"
$parcheT148 = "EIM - vigilante del conjunto (T148)"
if ($AlEncender) { $nombre = $nombreEncender }
if ($Vigilante) { $nombre = $nombreVigilante }

if ($Quitar) {
  Unregister-ScheduledTask -TaskName $nombre -Confirm:$false
  Write-Host "Tarea quitada: $nombre"
  return
}

if ($Vigilante) {
  # Cada 5 min, sin fin, desde dentro de un minuto: con `-Once` + repetición el disparador
  # salta aunque Windows ya esté encendido y la sesión abierta, que es justo lo que faltaba.
  # IgnoreNew: si una pasada se alarga (un arranque tarda minutos), la siguiente no se encima.
  $guion = Join-Path $PSScriptRoot "vigilante_conjunto.ps1"
  $accionV = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$guion`""
  $disparoV = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
  $ajustesV = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
  Register-ScheduledTask -TaskName $nombreVigilante -Action $accionV -Trigger $disparoV `
    -Settings $ajustesV -Force `
    -Description "Comprueba cada 5 min los cinco latidos del EIM y levanta los servicios de datos si falta alguno desde hace 10 min (T148). Tope de intentos, espera creciente y aviso al usuario." |
    Out-Null
  Write-Host "Tarea registrada: '$nombreVigilante' (cada 5 min, levanta tras 10 min sin latido)."
  if (Get-ScheduledTask -TaskName $parcheT148 -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $parcheT148 -Confirm:$false
    Write-Host "Parche provisional retirado: '$parcheT148' (lo sustituye la tarea de arriba)."
  }
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
