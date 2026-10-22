<#
.SYNOPSIS
  EQUIPO NUEVO (tras clonar y correr preparar_equipo.ps1): restaura el paquete creado por
  exportar_equipo.ps1: v2\data, variables EIM_* de usuario, .claude\settings.local.json y la
  memoria de Claude (ligada a la ruta de ESTE clon). Deja creado el acceso del escritorio.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\importar_equipo.ps1 -Origen D:\EIM_migracion
  ... -InicioAutomatico   # además registra el arranque con Windows
  ... -Forzar             # sobrescribe un v2\data que ya tenga contenido (queda en data.previa)
#>
param(
  [Parameter(Mandatory)][string]$Origen,
  [switch]$InicioAutomatico,
  [switch]$Forzar
)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$git = (git -C $v2 rev-parse --path-format=absolute --git-common-dir).Trim()
$raiz = (Resolve-Path (Split-Path -Parent $git)).Path
$Origen = (Resolve-Path $Origen).Path
if (-not (Test-Path (Join-Path $Origen "paquete.json"))) {
  throw "$Origen no es un paquete de exportar_equipo.ps1"
}

$patron = 'eim\.operation|eim\.leaders|eim\.api|uvicorn.*eim'
if (Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python\.exe$' -and $_.CommandLine -match $patron }) {
  throw "Hay servicios EIM corriendo; deténlos antes de importar."
}

# 1. data
$datos = Join-Path $raiz "v2\data"
$tiene = (Test-Path $datos) -and (Get-ChildItem $datos -Force | Select-Object -First 1)
if ($tiene) {
  if (-not $Forzar) { throw "$datos ya tiene contenido. Usa -Forzar para sobrescribirlo (queda en data.previa)." }
  $prev = "$datos.previa"
  if (Test-Path $prev) { Remove-Item $prev -Recurse -Force }
  Move-Item $datos $prev
}
robocopy (Join-Path $Origen "data") $datos /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy falló (código $LASTEXITCODE)" }
$a = Get-ChildItem (Join-Path $Origen "data") -Recurse -File -Force | Measure-Object Length -Sum
$b = Get-ChildItem $datos -Recurse -File -Force | Measure-Object Length -Sum
if ($a.Count -ne $b.Count -or $a.Sum -ne $b.Sum) { throw "Verificación de data fallida." }
Write-Host ("data restaurada: {0} archivos, {1:N1} MB." -f $b.Count, ($b.Sum / 1MB))

# 2. Variables EIM_* (nivel usuario)
$ef = Join-Path $Origen "env_EIM.json"
if (Test-Path $ef) {
  $vars = Get-Content $ef -Raw | ConvertFrom-Json
  foreach ($p in $vars.PSObject.Properties) {
    [Environment]::SetEnvironmentVariable($p.Name, [string]$p.Value, "User")
  }
  Write-Host "Variables EIM_* restauradas: $(@($vars.PSObject.Properties).Count). Abre una terminal nueva para verlas."
  if ($vars.EIM_SHARED_DIR -and -not (Test-Path $vars.EIM_SHARED_DIR)) {
    Write-Warning "EIM_SHARED_DIR apunta a $($vars.EIM_SHARED_DIR), que no existe en este equipo: corrígela."
  }
}

# 3. Claude: settings.local.json y memoria (con la ruta de ESTE clon)
$sl = Join-Path $Origen "settings.local.json"
if (Test-Path $sl) {
  New-Item -ItemType Directory -Force -Path (Join-Path $raiz ".claude") | Out-Null
  Copy-Item $sl (Join-Path $raiz ".claude\settings.local.json") -Force
  Write-Host "settings.local.json restaurado (revisa rutas absolutas del equipo anterior, si las hay)."
}
$mem = Join-Path $Origen "memory"
if (Test-Path $mem) {
  $slug = $raiz -replace '[^A-Za-z0-9]', '-'
  $dm = Join-Path $env:USERPROFILE ".claude\projects\$slug\memory"
  New-Item -ItemType Directory -Force -Path $dm | Out-Null
  robocopy $mem $dm /E /NFL /NDL /NP | Out-Null
  Write-Host "Memoria de Claude restaurada en $dm"
}

# 4. Acceso de escritorio e inicio automático
& (Join-Path $PSScriptRoot "crear_acceso_escritorio.ps1")
if ($InicioAutomatico) { & (Join-Path $PSScriptRoot "instalar_inicio_automatico.ps1") }
Write-Host "`nListo. Borra el paquete ($Origen): contiene claves en claro. Luego abre el icono EIM."
