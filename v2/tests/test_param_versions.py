"""T32: las versiones de parámetros publicadas son inmutables (cambiar = archivo nuevo).

Cada archivo de `eim/*/versions/` figura aquí con su SHA-256 sobre el contenido con fin de línea
LF (`.gitattributes` fija LF en el repositorio; el hash ignora un CRLF local de Windows).
Editar uno publicado rompe este test: crea `risk_v2.json` (o `params_v2_...json`) y registra su
hash en el mismo PR.
"""

import hashlib
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "eim"
PUBLISHED = {
    "calibration/versions/params_v1_btc_1h.json":
        "b8bdd3cd35684bd8d7b03a7b06dbf4e4bf3ab4690d19f42a90f1a809367c93a2",
    "risk/versions/risk_v1.json":
        "89b35f701c2371f057b404a0b6f87498d7cdd662197b619b1d165e86c4852684",
    "risk/versions/risk_copy_v1.json":  # T42: carril de copy trading simulado
        "765aa312533d81eb5de09d82e17e3df2e9de35d1d21e28a5b0a861f9f49e0eda",
}


def _lf(rel: str) -> bytes:
    return (PKG / rel).read_bytes().replace(b"\r\n", b"\n")


def test_every_version_is_registered():
    found = {p.relative_to(PKG).as_posix() for p in PKG.glob("*/versions/*.json")}
    assert found == set(PUBLISHED), "versión nueva o borrada: registrar su hash en PUBLISHED"


@pytest.mark.parametrize("rel", sorted(PUBLISHED))
def test_published_version_unchanged(rel):
    assert hashlib.sha256(_lf(rel)).hexdigest() == PUBLISHED[rel], f"{rel} editado: crea otra"


def test_risk_config_hash_ignores_line_endings(tmp_path):
    from eim.risk import load_config
    assert load_config().sha256 == PUBLISHED["risk/versions/risk_v1.json"]
    crlf = tmp_path / "risk_v1.json"
    crlf.write_bytes(_lf("risk/versions/risk_v1.json").replace(b"\n", b"\r\n"))
    assert load_config(crlf).sha256 == PUBLISHED["risk/versions/risk_v1.json"]
