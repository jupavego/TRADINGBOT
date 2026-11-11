"""T165: los scripts de PowerShell del proyecto se analizan (el gate no los veía).

`scripts/dvol_colector.ps1` se fusionó con un error de sintaxis —`"$py:"`, que PowerShell lee como
una variable con unidad— y ninguna prueba lo vio: el gate solo mira Python, así que un script del
proyecto puede entrar roto con el gate en verde. Aquí se le pide al propio PowerShell que
**analice** cada `.ps1` sin ejecutarlo (`[Parser]::ParseFile`), que es lo que separa «no se puede
ni leer» de «hace algo raro»; lo segundo no lo puede juzgar una prueba de sintaxis.

La orden se manda en base64 (`-EncodedCommand`) para que no dependa de cómo cite el intérprete
intermedio. Se omite donde no hay PowerShell (Linux, otro equipo): el archivo versionado es el
mismo y lo comprueba quien pueda ejecutarlo.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PS = shutil.which("powershell") or shutil.which("pwsh")
sin_powershell = pytest.mark.skipif(PS is None, reason="este equipo no tiene PowerShell")

_ANALIZA = """
$ErrorActionPreference = 'Stop'
foreach ($f in Get-ChildItem -LiteralPath '{carpeta}' -Filter *.ps1) {{
  $e = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    $f.FullName, [ref]$null, [ref]$e) | Out-Null
  foreach ($x in $e) {{
    Write-Output "$($f.Name):$($x.Extent.StartLineNumber): $($x.Message)"
  }}
}}
"""


def _problemas(carpeta: Path) -> list[str]:
    """Una línea `archivo:línea: mensaje` por error de análisis; lista vacía si todos analizan."""
    orden = _ANALIZA.format(carpeta=carpeta.as_posix().replace("'", "''"))
    codificada = base64.b64encode(orden.encode("utf-16-le")).decode("ascii")
    r = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-EncodedCommand", codificada],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        pytest.fail(f"PowerShell terminó con {r.returncode}: {r.stderr[:500]}")
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


@sin_powershell
def test_todos_los_scripts_de_powershell_analizan():
    nombres = sorted(p.name for p in SCRIPTS.glob("*.ps1"))
    assert nombres, f"ningún .ps1 en {SCRIPTS}: ¿se movió la carpeta?"
    problemas = _problemas(SCRIPTS)
    assert problemas == [], "scripts que no analizan:\n" + "\n".join(problemas)


@sin_powershell
def test_el_analisis_caza_el_fallo_que_se_colo(tmp_path):
    """Sin esto, la prueba de arriba pasaría igual aunque el análisis no mirara nada.

    El script de ejemplo es el error exacto que se fusionó: `$py:` dentro de una cadena.
    """
    (tmp_path / "roto.ps1").write_text('$py = "x"\nthrow "no existe $py: ya"\n', encoding="utf-8")
    (tmp_path / "bueno.ps1").write_text('$py = "x"\nWrite-Output "${py}; ya"\n', encoding="utf-8")
    problemas = _problemas(tmp_path)
    assert len(problemas) == 1, problemas
    assert problemas[0].startswith("roto.ps1:2:")
