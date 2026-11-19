<#
.SYNOPSIS
  T196 · Libro central entre equipos: configura la experiencia compartida en ESTE equipo con
  encendido programado. Se corre una vez en cada equipo (la portátil y juanpablo-cpu).

.DESCRIPTION
  1. Comprueba que el código ya trae T196 (si no, pide traer main antes).
  2. Comprueba que este equipo puede leer y escribir el repo PRIVADO de transporte
     (por defecto https://github.com/Santivego/eim-shared-data.git) con sus credenciales de git.
  3. `python -m eim.data.share setup --git-url <repo> --machine <alias> --start <fecha>`: el alias es
     el de siempre de este equipo (data/machine_id, o el de una configuración apartada el 2026-10-30).
     Hasta la fecha (por defecto 2026-11-28 00:00 UTC, el cierre de T31) el agente queda DORMIDO:
     ni importa ni exporta. Después se despierta solo, sin reiniciar.
  4. Reinicia los servicios (como «Reiniciar» del icono) para que la API lea la configuración,
     salvo con -SinReiniciar.
  Todo en modo SIMULADO; nunca viajan claves.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\activar_libro_central.ps1
  ... -Inicio 2026-11-28T00:00:00 -Repo https://github.com/Santivego/eim-shared-data.git
  ... -SinReiniciar      # lo reinicia otro script (p. ej. el despliegue de la portátil)
#>
param(
  [string]$Inicio = "2026-11-28T00:00:00",
  [string]$Repo = "https://github.com/Santivego/eim-shared-data.git",
  [string]$Alias = "",
  [switch]$SinReiniciar
)
$ErrorActionPreference = "Continue"
$v2 = Split-Path -Parent $PSScriptRoot
$datos = Join-Path $v2 "data"
$py = Join-Path $v2 ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONIOENCODING = "utf-8"
function Titulo([string]$t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Falla([string]$m) { Write-Host "NO SE ACTIVO: $m" -ForegroundColor Red; exit 1 }

Titulo "1. ¿El código trae T196?"
if (-not (Test-Path (Join-Path $v2 "eim\paper\provenance.py"))) {
  Falla "este equipo no tiene T196. Trae main primero (git pull origin main) y vuelve a correrlo."
}
Write-Host "sí (eim/paper/provenance.py)"

Titulo "2. Acceso al repo de transporte"
git ls-remote --heads $Repo 2>&1 | Select-Object -First 5
if ($LASTEXITCODE -ne 0) {
  Falla "git no puede leer $Repo con las credenciales de este equipo (pide acceso de escritura al dueño del repo o inicia sesión con 'gh auth login')."
}

Titulo "3. Alias de este equipo"
if (-not $Alias) {
  $apartada = Get-ChildItem $datos -Filter "share_config.json.*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($apartada) {
    try { $Alias = (Get-Content $apartada.FullName -Raw | ConvertFrom-Json).machine } catch { $Alias = "" }
    if ($Alias) { Write-Host "de la configuración apartada $($apartada.Name): $Alias" }
  }
}
if (-not $Alias -and (Test-Path (Join-Path $datos "machine_id"))) {
  $Alias = (Get-Content (Join-Path $datos "machine_id") -Raw).Trim()
  Write-Host "de data/machine_id: $Alias"
}
if (-not $Alias) { Falla "no encuentro el alias de este equipo; pásalo con -Alias <nombre>" }

Titulo "4. Configurar con encendido programado ($Inicio UTC)"
Push-Location $v2
& $py -m eim.data.share setup --git-url $Repo --machine $Alias --start $Inicio
$rc = $LASTEXITCODE
Pop-Location
if ($rc -ne 0) { Falla "el setup falló (código $rc); la salida está arriba" }
Get-Content (Join-Path $datos "share_config.json")

if ($SinReiniciar) { Write-Host "`nListo. Reinicia los servicios para que la API lea la configuración."; exit 0 }

Titulo "5. Reiniciar servicios"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "detener_servicio.ps1")
Start-Process powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
  (Join-Path $PSScriptRoot "servicio_continuo.ps1"), "-ConWeb") -WindowStyle Minimized
Write-Host "Servicios relanzados. En 2-3 min: GET http://127.0.0.1:8000/v2/share/status debe decir dormant=true hasta $Inicio UTC."
exit 0
