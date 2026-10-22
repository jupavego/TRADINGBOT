<#
.SYNOPSIS
  COLABORADOR QUE VUELVE tras varios días: respalda su versión local (datos de operación,
  trabajo sin confirmar, ramas, variables y configuración de Claude) y actualiza el clon al
  `main` de GitHub con las dependencias y el gate. No borra nada: todo queda en la carpeta de
  respaldo antes de tocar el repositorio. Guía: docs/RETOMAR_COLABORADOR.md.

  A diferencia de exportar_equipo.ps1 (traslado a otro equipo), este script NO quita el inicio
  automático ni se lleva las claves a otra máquina: respalda en sitio y sigue con la actualización.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\actualizar_colaborador.ps1
  ... -SoloRespaldo          # solo la copia: no toca git ni dependencias
  ... -Respaldo D:\EIM_respaldo_20261022
  ... -Todo                  # respalda también velas y derivados regenerables (lento, GB)
  ... -Forzar                # continúa aunque haya trabajo sin confirmar (ya respaldado)
  ... -SinGate               # salta ruff + pytest al final
#>
param(
  [string]$Respaldo,
  [switch]$SoloRespaldo,
  [switch]$Todo,
  [switch]$Forzar,
  [switch]$SinGate
)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$git = (git -C $v2 rev-parse --path-format=absolute --git-common-dir).Trim()
$raiz = (Resolve-Path (Split-Path -Parent $git)).Path          # checkout principal
$datos = Join-Path $raiz "v2\data"

function Comprueba([string]$paso) {
  if ($LASTEXITCODE -ne 0) { throw "$paso falló (código $LASTEXITCODE). Revisa la salida anterior." }
}
function Titulo([string]$t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

if (-not $Respaldo) {
  $Respaldo = Join-Path $env:USERPROFILE ("EIM_respaldos\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Force -Path $Respaldo | Out-Null
$Respaldo = (Resolve-Path $Respaldo).Path

# ---------------------------------------------------------------- 1. Estado antes de tocar nada
Titulo "Estado actual"
$rama = (git -C $raiz rev-parse --abbrev-ref HEAD).Trim()
$commit = (git -C $raiz rev-parse --short HEAD).Trim()
$sucio = @(git -C $raiz status --porcelain)
git -C $raiz fetch origin --quiet
$pendientes = @(git -C $raiz log --oneline HEAD..origin/main)
$sinSubir = @(git -C $raiz for-each-ref --format="%(refname:short)|%(upstream:short)|%(upstream:track)" refs/heads |
              ForEach-Object {
                $p = $_.Split("|")
                if (-not $p[1]) { "$($p[0]) (sin rama remota)" }
                elseif ($p[2] -match "ahead|gone") { "$($p[0]) $($p[2])" }
              })
Write-Host "Rama: $rama ($commit) · sin confirmar: $($sucio.Count) archivos"
Write-Host "origin/main trae $($pendientes.Count) commits nuevos"
if ($sinSubir) { Write-Host "Ramas locales sin subir o sin rastreo:`n  $($sinSubir -join "`n  ")" }

# ---------------------------------------------------------------- 2. Detener los servicios EIM
Titulo "Deteniendo servicios EIM (la copia tiene que ser en frío)"
$patron = 'eim\.operation|eim\.leaders|eim\.api|uvicorn.*eim'
foreach ($vuelta in 1..3) {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^python\.exe$' -and $_.CommandLine -match $patron } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 3
}
$vivos = @(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python\.exe$' -and $_.CommandLine -match $patron })
if ($vivos.Count) { throw "Siguen procesos EIM vivos (PID $($vivos.ProcessId -join ', ')). Ciérralos y repite." }
Write-Host "Servicios detenidos (el inicio automático NO se tocó: volverán al reiniciar o con el icono)."

# ---------------------------------------------------------------- 3. Respaldo
Titulo "Respaldo en $Respaldo"

# 3a. v2\data en frío, con verificación de archivos y bytes.
$destDatos = Join-Path $Respaldo "data"
$excluirDir = @()
$excluirFich = @("*.wal.bak")
if (-not $Todo) {
  $excluirDir = @("candles", "funding", "open_interest", "long_short_ratio", "liquidations", "micro",
                  "arbitrage", "obs", "obs_corrupto", "roadmap_live") | ForEach-Object { Join-Path $datos $_ }
}
if (Test-Path $datos) {
  $rc = @($datos, $destDatos, "/E", "/COPY:DAT", "/R:2", "/W:2", "/NFL", "/NDL", "/NP")
  if ($excluirDir) { $rc += "/XD"; $rc += $excluirDir }
  $rc += "/XF"; $rc += $excluirFich
  robocopy @rc | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy falló (código $LASTEXITCODE)" }
  $a = Get-ChildItem $datos -Recurse -File -Force | Where-Object {
    $f = $_.FullName; $n = $_.Name
    -not ($excluirDir | Where-Object { $f.StartsWith($_ + "\") }) -and
    -not ($excluirFich | Where-Object { $n -like $_ }) } | Measure-Object Length -Sum
  $b = Get-ChildItem $destDatos -Recurse -File -Force | Measure-Object Length -Sum
  if ($a.Count -ne $b.Count -or $a.Sum -ne $b.Sum) {
    throw "Verificación fallida: origen $($a.Count) arch/$($a.Sum) B, copia $($b.Count)/$($b.Sum)."
  }
  Write-Host ("data: {0} archivos, {1:N1} MB verificados." -f $b.Count, ($b.Sum / 1MB))
} else {
  Write-Warning "No existe ${datos}: no hay historial de operación que respaldar (clon sin usar)."
}

# 3b. Copia consistente de la base con el propio sistema (manifest con SHA-256 y filas por tabla).
$venvPy = Join-Path $raiz "v2\.venv\Scripts\python.exe"
if ((Test-Path $venvPy) -and (Test-Path (Join-Path $datos "reports.duckdb"))) {
  Push-Location (Join-Path $raiz "v2")
  try {
    & $venvPy -m eim.data.backup create
    if ($LASTEXITCODE -eq 0) {
      & $venvPy -m eim.data.backup verify
      if ($LASTEXITCODE -ne 0) { Write-Warning "La copia de eim.data.backup no verificó." }
    } else { Write-Warning "eim.data.backup create falló; queda la copia en frío de 3a." }
  } finally { Pop-Location }
} else {
  Write-Host "Sin entorno virtual o sin reports.duckdb: me quedo con la copia en frío."
}

# 3c. Trabajo sin confirmar y ramas locales (lo que no está en GitHub).
git -C $raiz status --porcelain | Set-Content (Join-Path $Respaldo "estado_git.txt") -Encoding utf8
git -C $raiz diff HEAD | Set-Content (Join-Path $Respaldo "cambios_sin_confirmar.patch") -Encoding utf8
git -C $raiz ls-files --others --exclude-standard |
  Set-Content (Join-Path $Respaldo "archivos_nuevos_sin_seguir.txt") -Encoding utf8
git -C $raiz bundle create (Join-Path $Respaldo "ramas_locales.bundle") --branches 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "Ramas locales guardadas en ramas_locales.bundle" }
Write-Host "Trabajo sin confirmar guardado (parche + lista de archivos nuevos)."

# 3d. Variables EIM_* del usuario (pueden contener claves de testnet).
$vars = [ordered]@{}
foreach ($kv in [Environment]::GetEnvironmentVariables("User").GetEnumerator() | Sort-Object Name) {
  if ($kv.Key -like "EIM_*") { $vars[$kv.Key] = [string]$kv.Value }
}
$vars | ConvertTo-Json | Set-Content (Join-Path $Respaldo "env_EIM.json") -Encoding utf8
Write-Host "Variables EIM_*: $($vars.Count)"

# 3e. Configuración y memoria de Claude Code.
$cl = Join-Path $raiz ".claude\settings.local.json"
if (Test-Path $cl) { Copy-Item $cl (Join-Path $Respaldo "settings.local.json") -Force }
$slug = $raiz -replace '[^A-Za-z0-9]', '-'
$mem = Join-Path $env:USERPROFILE ".claude\projects\$slug\memory"
if (Test-Path $mem) { robocopy $mem (Join-Path $Respaldo "memory") /E /NFL /NDL /NP | Out-Null }

@{ fecha = (Get-Date -Format s); equipo = $env:COMPUTERNAME; raiz = $raiz; rama = $rama
   commit = $commit; sin_confirmar = $sucio.Count; todo = [bool]$Todo } |
  ConvertTo-Json | Set-Content (Join-Path $Respaldo "respaldo.json") -Encoding utf8
Write-Host "Respaldo completo. Contiene las variables EIM_* en claro: no lo subas a Git ni a una carpeta compartida."

if ($SoloRespaldo) {
  Write-Host "`n-SoloRespaldo: no toco el repositorio. Respaldo en $Respaldo" -ForegroundColor Green
  exit 0
}

# ---------------------------------------------------------------- 4. Actualizar el código
Titulo "Actualizando el código"
if ($sucio.Count -and -not $Forzar) {
  throw ("Hay $($sucio.Count) archivos sin confirmar. Ya están respaldados en $Respaldo. " +
         "Confírmalos en una rama y súbelos, o repite con -Forzar (quedarán tal cual, sin fusionar).")
}
if ($rama -ne "main") {
  Write-Host "Estás en '$rama'; me quedo en ella y traigo main aparte."
  git -C $raiz pull --ff-only origin main
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "No se pudo adelantar '$rama' con main sin fusionar. Haz tú: git switch main; git pull"
  }
} else {
  git -C $raiz pull --ff-only; Comprueba "git pull --ff-only"
}
Write-Host ("Ahora en " + (git -C $raiz rev-parse --short HEAD).Trim())

# ---------------------------------------------------------------- 5. Dependencias
Titulo "Dependencias (hay paquetes nuevos: scipy es obligatorio desde esta semana)"
Push-Location (Join-Path $raiz "v2")
try {
  if (-not (Test-Path ".venv")) { python -m venv .venv; Comprueba "python -m venv" }
  $venvPy = Join-Path $raiz "v2\.venv\Scripts\python.exe"
  & $venvPy -m pip install -U pip; Comprueba "pip install -U pip"
  & $venvPy -m pip install -r requirements-lock.txt; Comprueba "pip install -r requirements-lock.txt"
  & $venvPy -m pip install -e . --no-deps; Comprueba "pip install -e ."   # pytest/ruff vienen del lock
  Push-Location eim\web
  try { npm ci; Comprueba "npm ci" } finally { Pop-Location }

  # -------------------------------------------------------------- 6. Gate
  if (-not $SinGate) {
    Titulo "Gate"
    & $venvPy -m ruff check eim tests; Comprueba "ruff check"
    & $venvPy -m pytest -q
    if ($LASTEXITCODE -ne 0) {
      Write-Warning ("El gate falló. Antes de dar por mala la actualización mira " +
                     "docs/RETOMAR_COLABORADOR.md §5 (pruebas sensibles al equipo).")
    }
  }
} finally { Pop-Location }

Titulo "Listo"
Write-Host "Respaldo: $Respaldo"
Write-Host "Siguiente: docs/RETOMAR_COLABORADOR.md §4 (datos y experiencia) y §6 (arrancar)."
