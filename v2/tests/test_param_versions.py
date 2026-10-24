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
    "risk/versions/risk_v2.json":  # T44: tamaño ×0.5 en ventana de evento (vigente)
        "8b2f9b1203bd1a0e8ef205a7fc0b15d601d61bdf1a6285e62a2f63105ff42cf2",
    "risk/versions/risk_arb_v1.json":  # T45: arbitraje en testnet (dos patas)
        "25ddd58223056d7b6c23548b56d440ee636a55540ee909200eab014a82a79e7b",
    "risk/versions/risk_arb_sim_v1.json":  # T45: arbitraje en el bróker simulado
        "ec1087e59466a25ec91846f840fc41feded0ea17f8ab0dc6339a12f55607ae0e",
    "risk/versions/hft_risk_v1.json":  # T83: riesgo del carril HFT (SIMULADO/TESTNET)
        "f47163657cd4e987a75f87b2173c77eb1edfacdd47b1ca212e64ff849897d380",
    "validation/versions/validation_v1.json":  # T49: criterios de la puerta de validación
        "0a5b19962ded0d12dfdbccac0359f91c1bebf211ed891f7817c96667e01c30a8",
    "forecast/versions/lit_tilt_v1.json":  # T54: definición del ajuste bibliográfico (apagado)
        "b7659f79ce4a6f031b564834ba09bf73dcd06c7d07127770bfcae82faff094a1",
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
    assert load_config().sha256 == PUBLISHED["risk/versions/risk_v2.json"]
    crlf = tmp_path / "risk_v2.json"
    crlf.write_bytes(_lf("risk/versions/risk_v2.json").replace(b"\n", b"\r\n"))
    assert load_config(crlf).sha256 == PUBLISHED["risk/versions/risk_v2.json"]
    assert load_config(version="risk_v1").event_size_factor == 1.0   # v1 conserva su efecto
