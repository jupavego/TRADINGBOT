<#
.SYNOPSIS
  Publica el estado de este equipo (T125): copia completa verificada -> copia externa en el repo
  privado de datos -> exportación de la experiencia (desde la copia) -> aviso del código sin
  subir. Lo ejecuta cada día la tarea «EIM - copia externa diaria» (instalar_copia_externa.ps1);
  también a mano antes de cambiar de equipo. Registro: data\operation\logs\copia_externa.log y
  data\continuity\publish.jsonl. Nunca arranca, para ni reinicia servicios.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\copia_externa.ps1
#>
param([string]$DataDir = "", [switch]$SinExperiencia)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$py = Join-Path $v2 ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not $DataDir) { $DataDir = Join-Path $v2 "data" }
$logs = Join-Path $DataDir "operation\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs "copia_externa.log"
$env:PYTHONIOENCODING = "utf-8"
# La consola oculta de la tarea usa ibm850: sin esto, la salida UTF-8 de Python llega al registro
# con los acentos rotos («verificaci├│n»).
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$argv = @("-m", "eim.continuity", "--data-dir", $DataDir, "publish")
if ($SinExperiencia) { $argv += "--no-share" }
Push-Location $v2
try {
  # PowerShell 5.1 convierte el stderr de un ejecutable en error: con "Stop" cortaría la copia.
  $ErrorActionPreference = "Continue"
  "=== $(Get-Date -Format o) ===" | Out-File -Append -Encoding utf8 $log
  & $py @argv 2>&1 | Out-File -Append -Encoding utf8 $log
  $code = $LASTEXITCODE
  "salida $code" | Out-File -Append -Encoding utf8 $log
} finally { Pop-Location }
exit $code
