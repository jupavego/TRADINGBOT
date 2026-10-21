<#
.SYNOPSIS
  EQUIPO ANTIGUO: detiene el servicio y empaqueta en una carpeta de traslado (disco externo o
  nube) todo lo que NO viaja con git: v2\data (copia en frío), variables EIM_* del usuario,
  .claude\settings.local.json y la memoria de Claude. Verifica la copia con recuento de
  archivos y bytes. Pareja de importar_equipo.ps1. Guía: docs/MIGRACION_EQUIPO.md.

  ATENCIÓN: el paquete contiene las claves EIM_* en claro. Guárdalo en un disco propio y bórralo
  tras importar. Nunca lo subas a Git ni a una carpeta compartida.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File v2\scripts\exportar_equipo.ps1 -Destino D:\EIM_migracion
  ... -Todo                 # incluye también velas y datos regenerables
  ... -ConservarMiIdentidad # no copia machine_id/EIM_MACHINE (el equipo nuevo tendrá identidad propia)
#>
param(
  [Parameter(Mandatory)][string]$Destino,
  [switch]$Todo,
  [switch]$ConservarMiIdentidad
)
$ErrorActionPreference = "Stop"
$v2 = Split-Path -Parent $PSScriptRoot
$git = (git -C $v2 rev-parse --path-format=absolute --git-common-dir).Trim()
$raiz = (Resolve-Path (Split-Path -Parent $git)).Path          # checkout principal
$datos = Join-Path $raiz "v2\data"
if (-not (Test-Path $datos)) { throw "No existe $datos" }
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$Destino = (Resolve-Path $Destino).Path

# 1. Detener todo (vigilante primero, para que no relance la API) y el inicio automático.
Write-Host "Deteniendo servicios EIM..."
$patron = 'eim\.operation|eim\.leaders|eim\.api|uvicorn.*eim'
foreach ($vuelta in 1..3) {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^python\.exe$' -and $_.CommandLine -match $patron } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 3
}
try { & (Join-Path $PSScriptRoot "instalar_inicio_automatico.ps1") -Quitar | Out-Null } catch {}  # ya quitado: repetir no falla
$vivos = @(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python\.exe$' -and $_.CommandLine -match $patron })
if ($vivos.Count) { throw "Siguen procesos EIM vivos (PID $($vivos.ProcessId -join ', ')). Ciérralos y repite." }

# 2. v2\data en frío (sin velas ni derivados regenerables, salvo -Todo).
$dest = Join-Path $Destino "data"
$excluirDir = @()
$excluirFich = @("*.wal.bak")
if (-not $Todo) {
  $excluirDir = @("candles", "funding", "open_interest", "long_short_ratio", "liquidations", "micro",
                  "arbitrage", "obs", "obs_corrupto", "roadmap_live") | ForEach-Object { Join-Path $datos $_ }
}
if ($ConservarMiIdentidad) { $excluirFich += @("machine_id", "share_config.json") }
$rc = @($datos, $dest, "/E", "/COPY:DAT", "/R:2", "/W:2", "/NFL", "/NDL", "/NP")
if ($excluirDir) { $rc += "/XD"; $rc += $excluirDir }
$rc += "/XF"; $rc += $excluirFich
robocopy @rc | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy falló (código $LASTEXITCODE)" }

# Verificación: mismo nº de archivos y bytes que el origen ya filtrado.
$a = Get-ChildItem $datos -Recurse -File -Force | Where-Object {
  $f = $_.FullName; $n = $_.Name
  -not ($excluirDir | Where-Object { $f.StartsWith($_ + "\") }) -and
  -not ($excluirFich | Where-Object { $n -like $_ }) } | Measure-Object Length -Sum
$b = Get-ChildItem $dest -Recurse -File -Force | Measure-Object Length -Sum
if ($a.Count -ne $b.Count -or $a.Sum -ne $b.Sum) {
  throw "Verificación fallida: origen $($a.Count) arch/$($a.Sum) B, copia $($b.Count)/$($b.Sum)."
}
Write-Host ("data: {0} archivos, {1:N1} MB verificados." -f $b.Count, ($b.Sum / 1MB))

# 3. Variables EIM_* del usuario.
$vars = [ordered]@{}
foreach ($kv in [Environment]::GetEnvironmentVariables("User").GetEnumerator() | Sort-Object Name) {
  if ($kv.Key -like "EIM_*" -and -not ($ConservarMiIdentidad -and $kv.Key -eq "EIM_MACHINE")) {
    $vars[$kv.Key] = [string]$kv.Value
  }
}
$vars | ConvertTo-Json | Set-Content (Join-Path $Destino "env_EIM.json") -Encoding utf8
Write-Host "Variables EIM_*: $($vars.Count) ($($vars.Keys -join ', '))"

# 4. Configuración local de Claude Code y memoria.
$cl = Join-Path $raiz ".claude\settings.local.json"
if (Test-Path $cl) {
  Copy-Item $cl (Join-Path $Destino "settings.local.json") -Force
  Write-Host "settings.local.json copiado."
}
$slug = $raiz -replace '[^A-Za-z0-9]', '-'
$mem = Join-Path $env:USERPROFILE ".claude\projects\$slug\memory"
if (Test-Path $mem) {
  robocopy $mem (Join-Path $Destino "memory") /E /NFL /NDL /NP | Out-Null
  Write-Host "Memoria de Claude copiada ($mem)."
} else { Write-Warning "No hallé memoria de Claude en $mem" }

@{ fecha = (Get-Date -Format s); equipo = $env:COMPUTERNAME; raiz = $raiz; todo = [bool]$Todo } |
  ConvertTo-Json | Set-Content (Join-Path $Destino "paquete.json") -Encoding utf8
Write-Host "`nPaquete listo en $Destino. Llévalo al equipo nuevo y ejecuta importar_equipo.ps1."
Write-Host "Contiene claves en claro: bórralo al terminar. El inicio automático quedó quitado en este equipo."
