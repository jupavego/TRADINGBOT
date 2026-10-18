<#
.SYNOPSIS
  Crea (o quita con -Quitar) el acceso directo «EIM» en el escritorio del usuario actual, con el
  icono de la esfera (`esfera.ico`, captura de la esfera del río de decisión). Un doble clic
  ejecuta `abrir_interfaz.ps1`: arranca la API y la web si hace falta y abre la interfaz.
  Apunta a este repositorio por su ruta: si se mueve la carpeta, volver a ejecutarlo.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\crear_acceso_escritorio.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\crear_acceso_escritorio.ps1 -Quitar
#>
param([switch]$Quitar)
$ErrorActionPreference = "Stop"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "EIM.lnk"

if ($Quitar) {
  if (Test-Path $lnk) { Remove-Item $lnk }
  Write-Host "Acceso directo quitado: $lnk"
  return
}

$acceso = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$acceso.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$acceso.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'abrir_interfaz.ps1')`""
$acceso.WorkingDirectory = Split-Path -Parent $PSScriptRoot
$acceso.IconLocation = "$(Join-Path $PSScriptRoot 'esfera.ico'),0"
$acceso.Description = "Abre la interfaz del EIM (arranca la API y la web si hace falta)"
$acceso.Save()
Write-Host "Acceso directo creado: $lnk"
