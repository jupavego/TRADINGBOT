<#
.SYNOPSIS
  Icono del EIM junto al reloj (bandeja del sistema). Sustituye a la consola de PowerShell que
  dejaba abierta `abrir_interfaz.ps1`: el color del icono dice si el servicio responde, el globo
  avisa cuando cambia de estado y el menu derecho abre la interfaz, la hoja de ruta y los
  registros. Cerrar el icono NO para el servicio (para eso esta su opcion en el menu).

.DESCRIPTION
  Consulta `GET /v2/health` cada `-CadaS` segundos. Icono a color = la API responde; icono
  apagado = no responde (arrancando, caida o detenida). No abre ninguna ventana: se lanza con
  `eim_oculto.vbs` para que no parpadee ni una consola.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File v2\scripts\icono_bandeja.ps1
  wscript.exe v2\scripts\eim_oculto.vbs v2\scripts\icono_bandeja.ps1
#>
param([int]$Puerto = 8000, [int]$CadaS = 15)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$scripts = $PSScriptRoot
$v2 = Split-Path -Parent $scripts
$logs = Join-Path $v2 "data\operation\logs"
$api = "http://127.0.0.1:$Puerto/v2/health"
$web = "http://127.0.0.1:5173"
$ruta = "http://127.0.0.1:8765/roadmap.html"

# Un solo icono a la vez: si ya hay otro corriendo, este se va sin molestar.
# "Local\" basta (uno por sesion de usuario) y no pide privilegios como "Global\".
$nuevo = $false
$cerrojo = New-Object System.Threading.Mutex($true, "Local\EIM_icono_bandeja", [ref]$nuevo)
if (-not $nuevo) { return }

# --- iconos: el de la esfera y una copia apagada (gris y translucida) para "sin respuesta" ---
$icoVivo = New-Object System.Drawing.Icon (Join-Path $scripts "esfera.ico")
function Apagado([System.Drawing.Icon]$ico) {
  $bmp = $ico.ToBitmap()
  $out = New-Object System.Drawing.Bitmap $bmp.Width, $bmp.Height
  $g = [System.Drawing.Graphics]::FromImage($out)
  $m = New-Object 'System.Single[][]' 5
  for ($i = 0; $i -lt 5; $i++) { $m[$i] = New-Object 'System.Single[]' 5 }
  $m[0][0] = 0.299; $m[0][1] = 0.299; $m[0][2] = 0.299
  $m[1][0] = 0.587; $m[1][1] = 0.587; $m[1][2] = 0.587
  $m[2][0] = 0.114; $m[2][1] = 0.114; $m[2][2] = 0.114
  $m[3][3] = 0.45
  $m[4][4] = 1
  $ia = New-Object System.Drawing.Imaging.ImageAttributes
  # La coma unaria evita que PowerShell desempaquete el array escalonado en 5 argumentos.
  $ia.SetColorMatrix((New-Object System.Drawing.Imaging.ColorMatrix -ArgumentList (, $m)))
  $r = New-Object System.Drawing.Rectangle 0, 0, $bmp.Width, $bmp.Height
  $g.DrawImage($bmp, $r, 0, 0, $bmp.Width, $bmp.Height, [System.Drawing.GraphicsUnit]::Pixel, $ia)
  $g.Dispose(); $bmp.Dispose()
  [System.Drawing.Icon]::FromHandle($out.GetHicon())
}
$icoMuerto = Apagado $icoVivo

# --- menu ---
$menu = New-Object System.Windows.Forms.ContextMenuStrip
function Opcion([string]$texto, [scriptblock]$hacer) {
  $i = $menu.Items.Add($texto); $i.add_Click($hacer); $i
}
$mEstado = Opcion "Comprobando..." { }
$mEstado.Enabled = $false
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
Opcion "Abrir interfaz" { Start-Process $web } | Out-Null
Opcion "Hoja de ruta" { Start-Process $ruta } | Out-Null
Opcion "Ver registros" { if (Test-Path $logs) { Start-Process explorer.exe $logs } } | Out-Null
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$mArrancar = Opcion "Arrancar servicio" {
  Start-Process wscript.exe -ArgumentList @(
    ('"' + (Join-Path $scripts "eim_oculto.vbs") + '"'),
    ('"' + (Join-Path $scripts "servicio_continuo.ps1") + '"'), "-ConWeb")
}
$mParar = Opcion "Parar servicio" {
  $r = [System.Windows.Forms.MessageBox]::Show(
    "Se detendra la operacion en papel, los lideres y la interfaz. El icono sigue aqui.",
    "EIM - parar el servicio", "YesNo", "Warning")
  if ($r -ne "Yes") { return }
  $patron = 'eim\.operation|eim\.leaders|eim\.api|eim\.data\.micro|uvicorn.*eim|mantener_despierto|eim\.web'
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(python|node|powershell)\.exe$' -and $_.CommandLine -match $patron } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
Opcion "Quitar el icono (el servicio sigue)" {
  $icono.Visible = $false; [System.Windows.Forms.Application]::Exit()
} | Out-Null

# --- icono ---
$icono = New-Object System.Windows.Forms.NotifyIcon
$icono.Icon = $icoMuerto
$icono.Text = "EIM - comprobando..."
$icono.ContextMenuStrip = $menu
$icono.Visible = $true
$icono.add_MouseDoubleClick({ Start-Process $web })

$anterior = $null
function Revisar {
  $vivo = $false; $detalle = "sin respuesta"
  try {
    $h = Invoke-RestMethod $api -TimeoutSec 4
    $vivo = $true
    $op = if ($h.operation -eq "apagado") { "operacion apagada" } else { "operando" }
    $detalle = "$($h.mode) - $op - $($h.agents) agentes"
  } catch { }

  $icono.Icon = if ($vivo) { $icoVivo } else { $icoMuerto }
  # NotifyIcon.Text no admite mas de 63 caracteres.
  $t = if ($vivo) { "EIM activo - $detalle" } else { "EIM detenido - la API no responde" }
  if ($t.Length -gt 63) { $t = $t.Substring(0, 60) + "..." }
  $icono.Text = $t
  $mEstado.Text = $t
  $mArrancar.Enabled = -not $vivo
  $mParar.Enabled = $vivo

  if ($null -ne $script:anterior -and $script:anterior -ne $vivo) {
    $icono.BalloonTipTitle = if ($vivo) { "EIM activo" } else { "EIM sin respuesta" }
    $icono.BalloonTipText = $detalle
    $icono.ShowBalloonTip(4000)
  }
  $script:anterior = $vivo
}

$reloj = New-Object System.Windows.Forms.Timer
$reloj.Interval = [Math]::Max(5, $CadaS) * 1000
$reloj.add_Tick({ Revisar })
$reloj.Start()
Revisar

try { [System.Windows.Forms.Application]::Run() }
finally {
  $reloj.Stop(); $icono.Visible = $false; $icono.Dispose()
  $cerrojo.ReleaseMutex(); $cerrojo.Dispose()
}
