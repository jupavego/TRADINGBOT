<#
.SYNOPSIS
  Prepara un equipo nuevo tras clonar el repositorio: comprueba herramientas, crea el entorno
  virtual con las versiones probadas (`requirements-lock.txt`), instala la web (`npm ci`) y corre
  el gate. No toca datos de operación (ver docs/MIGRACION_EQUIPO.md para trasladarlos).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\preparar_equipo.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\preparar_equipo.ps1 -SinGate
#>
param([switch]$SinGate)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot

function Requiere([string]$cmd, [string]$ayuda) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Falta '$cmd'. $ayuda" }
}
Requiere git "winget install Git.Git"
Requiere python "winget install Python.Python.3.12 (marca Add to PATH)"
Requiere node "winget install OpenJS.NodeJS.LTS"
Requiere gh "winget install GitHub.cli"

$py = [version](python -c "import sys;print('%d.%d'%sys.version_info[:2])")
if ($py -lt [version]"3.11") { throw "Se necesita Python >= 3.11 (probado con 3.12); hay $py." }
if ([int](node -p "process.versions.node.split('.')[0]") -lt 20) { throw "Se necesita Node >= 20." }

Push-Location $v2
try {
  git config --global --add safe.directory "*"
  if (-not (Test-Path .venv)) { python -m venv .venv }
  $venvPy = Join-Path $v2 ".venv\Scripts\python.exe"
  & $venvPy -m pip install -U pip
  & $venvPy -m pip install -r requirements-lock.txt
  & $venvPy -m pip install -e . --no-deps
  Push-Location eim\web; npm ci; Pop-Location
  if (-not $SinGate) {
    & $venvPy -m ruff check eim tests
    & $venvPy -m pytest -q
  }
  Write-Host "`nEquipo listo. Siguiente: restaurar datos (docs/MIGRACION_EQUIPO.md) y crear_acceso_escritorio.ps1."
} finally { Pop-Location }
