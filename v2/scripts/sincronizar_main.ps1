<#
.SYNOPSIS
  Mantiene el checkout principal al día con `origin/main`, para que la interfaz del icono del
  escritorio muestre lo que se fusiona en GitHub (p. ej. los PR que hace Claude). Lo llaman el
  acceso del escritorio (`abrir_interfaz.ps1`, al abrir) y el icono de la bandeja (cada 5 min y
  con «Actualizar desde GitHub»).

.DESCRIPTION
  Seguro por diseño: solo avanza con fast-forward y nunca descarta trabajo.
  - En `main` sin cambios sin confirmar y sin commits propios: `git merge --ff-only origin/main`.
  - En otra rama: solo pasa a `main` si esa rama ya está entera dentro de `origin/main` (fusionada)
    y no hay cambios sin confirmar; si no, no toca nada y lo dice.
  - Con cambios sin confirmar en archivos del repo: no toca nada y lo dice (los archivos nuevos sin
    rastrear no cuentan; si el avance los pisara, git se niega solo).
  Tras avanzar:
  - La web (Vite en modo dev) recarga sola con el código nuevo.
  - Si cambió código de Python de `v2/eim/` (fuera de `web/`), reinicia SOLO la API (uvicorn): el
    vigilante la relanza al momento con el código nuevo (-SinReiniciar lo evita). El vigilante y
    los recolectores siguen con el código anterior hasta «Parar» + «Arrancar servicio».
  - Si cambió `v2/eim/web/package-lock.json`, corre `npm install` en la web.
  - Si cambiaron las dependencias de Python, lo avisa: hay que correr `actualizar_colaborador.ps1`.
  Deja el resultado en `v2/data/operation/sync_main.json` (lo lee el icono de la bandeja para
  avisar) y una línea por vuelta en `v2/data/operation/logs/sync_main.log`. Git va sin preguntas:
  si pide credenciales, falla y lo registra en vez de quedarse esperando.

  Termina con `exit`: lánzalo siempre como proceso aparte (`powershell -File ...`), no con `&`.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\sincronizar_main.ps1
  powershell -ExecutionPolicy Bypass -File v2\scripts\sincronizar_main.ps1 -SinReiniciar
#>
param([switch]$SinReiniciar, [int]$PuertoApi = 8000)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Una sola sincronización a la vez (acceso del escritorio + icono de la bandeja).
$nuevo = $false
$cerrojo = New-Object System.Threading.Mutex($true, "Local\EIM_sincronizar_main", [ref]$nuevo)
if (-not $nuevo) { Write-Host "Ya hay una sincronización en curso."; return }

# Nada de diálogos de credenciales ni prompts en una ejecución oculta.
$env:GIT_TERMINAL_PROMPT = "0"
$env:GCM_INTERACTIVE = "never"

$v2 = Split-Path -Parent $PSScriptRoot
$common = (git -C $v2 rev-parse --path-format=absolute --git-common-dir).Trim()
$raiz = (Resolve-Path (Split-Path -Parent $common)).Path     # checkout principal, aunque se llame desde un worktree
$opDir = Join-Path $raiz "v2\data\operation"
$logDir = Join-Path $opDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$res = [ordered]@{
  at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  status = "error"; branch = ""; from = ""; to = ""; commits = 0
  api_restarted = $false; npm_install = $false; python_deps = $false; message = ""
}

function G {
  # git sin excepciones: devuelve la salida y deja el código en $LASTEXITCODE.
  $ErrorActionPreference = "Continue"
  $out = & git -C $raiz @args 2>&1
  $out | ForEach-Object { "$_" }
}

function Terminar([string]$estado, [string]$mensaje) {
  $res.status = $estado; $res.message = $mensaje
  $json = $res | ConvertTo-Json -Compress
  [System.IO.File]::WriteAllText((Join-Path $opDir "sync_main.json"), $json, (New-Object System.Text.UTF8Encoding($false)))
  Add-Content -Path (Join-Path $logDir "sync_main.log") -Value "$($res.at) [$estado] $mensaje" -Encoding utf8
  Write-Host "[$estado] $mensaje"
  $cerrojo.ReleaseMutex(); $cerrojo.Dispose()
  exit 0
}

try {
  G -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 fetch --quiet origin main | Out-Null
  if ($LASTEXITCODE -ne 0) { Terminar "error" "No se pudo consultar GitHub (sin red o sin credenciales)." }

  $rama = ((G rev-parse --abbrev-ref HEAD) -join "").Trim()
  $res.branch = $rama
  $antes = ((G rev-parse HEAD) -join "").Trim()
  $remoto = ((G rev-parse origin/main) -join "").Trim()
  $res.from = $antes.Substring(0, 7); $res.to = $remoto.Substring(0, 7)

  $sucio = @(G status --porcelain --untracked-files=no | Where-Object { $_ })
  if ($sucio.Count -gt 0) {
    Terminar "skipped" "Hay $($sucio.Count) archivos con cambios sin confirmar en '$rama': no se actualiza para no pisarlos."
  }

  G merge-base --is-ancestor HEAD origin/main | Out-Null
  $incluida = ($LASTEXITCODE -eq 0)
  if ($rama -ne "main") {
    if (-not $incluida) {
      Terminar "skipped" "Estás en la rama '$rama' con trabajo que no está en main: no se cambia de rama."
    }
    G switch main | Out-Null
    if ($LASTEXITCODE -ne 0) { Terminar "error" "No se pudo pasar de '$rama' a main." }
    $res.branch = "main"
    $antes = ((G rev-parse HEAD) -join "").Trim()
    $res.from = $antes.Substring(0, 7)
    G merge-base --is-ancestor HEAD origin/main | Out-Null
    $incluida = ($LASTEXITCODE -eq 0)
  }
  if (-not $incluida) {
    Terminar "skipped" "main tiene commits locales que no están en GitHub: no se actualiza (súbelos o resuélvelo a mano)."
  }
  if ($antes -eq $remoto) {
    $res.to = $res.from
    Terminar "up_to_date" "Al día con GitHub (main $($res.from))."
  }

  $res.commits = [int](((G rev-list --count "$antes..$remoto") -join "").Trim())
  G merge --ff-only --quiet origin/main | Out-Null
  if ($LASTEXITCODE -ne 0) { Terminar "error" "git no pudo avanzar main (¿archivos sin rastrear que se pisarían?). Revisa con 'git status'." }

  $cambios = @(G diff --name-only $antes $remoto | Where-Object { $_ })
  $extra = @()

  if ($cambios -contains "v2/eim/web/package-lock.json") {
    $web = Join-Path $raiz "v2\eim\web"
    Push-Location $web
    try { & npm install --no-audit --no-fund 2>&1 | Out-Null; $res.npm_install = ($LASTEXITCODE -eq 0) } catch { } finally { Pop-Location }
    if ($res.npm_install) { $extra += "dependencias de la web instaladas" } else { $extra += "falló 'npm install' en la web" }
  }

  if (@($cambios | Where-Object { $_ -match '^v2/(pyproject\.toml|requirements[^/]*\.txt)$' }).Count -gt 0) {
    $res.python_deps = $true
    $extra += "cambiaron las dependencias de Python: corre v2\scripts\actualizar_colaborador.ps1"
  }

  $py = @($cambios | Where-Object { $_ -match '^v2/eim/.*\.py$' -and $_ -notmatch '^v2/eim/web/' })
  if ($py.Count -gt 0) {
    if ($SinReiniciar) {
      $extra += "hay cambios de la API: se aplican al reiniciar el servicio"
    } else {
      $api = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -match '-m\s+uvicorn\s+eim\.api\.main:app' -and $_.CommandLine -match "--port\s+$PuertoApi(\s|$)" })
      if ($api.Count -gt 0) {
        $api | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        $res.api_restarted = $true
        $extra += "API reiniciada con el código nuevo (la relanza el vigilante)"
      } else {
        $extra += "hay cambios de la API: se aplican cuando arranque el servicio"
      }
    }
  }

  $msg = "main actualizado: $($res.commits) commits nuevos ($($res.from) -> $($res.to))."
  if ($extra.Count -gt 0) { $msg += " " + ($extra -join "; ") + "." }
  Terminar "updated" $msg
} catch {
  Terminar "error" "Fallo inesperado: $_"
}
