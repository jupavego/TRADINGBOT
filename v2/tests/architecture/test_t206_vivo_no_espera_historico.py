"""T206: la mesa se pone en vivo sin esperar al histórico.

`load()` abría el WebSocket **después** de `await fetchSnapshot(...)`, así que con el snapshot
lento (medido: 14 s de trabajo, y entre 30 y 93 s en la API viva bajo carga) la barra se quedaba
en «Sin conexión» con el precio en `—` todo ese rato, aunque la API estuviera sana. Y el fallo del
histórico escribía en el mismo `#banner` que pinta `paintLive`, así que un aviso tapaba al otro.

Esto es un guardián de regresión sobre la fuente: lo que se ve en pantalla se comprueba en el
navegador (regla del proyecto), pero el orden de estas dos llamadas no puede volver a invertirse
sin que una prueba lo diga.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "eim" / "web"
MAIN = WEB / "src" / "main.ts"
INDEX = WEB / "index.html"


@pytest.fixture(scope="module")
def load_body() -> str:
    """El cuerpo de `async function load()`, hasta la siguiente función de primer nivel."""
    src = MAIN.read_text(encoding="utf-8")
    i = src.index("async function load()")
    j = src.index("\nfunction ", i)
    return src[i:j]


def test_el_socket_se_abre_antes_de_esperar_el_snapshot(load_body: str) -> None:
    abre = load_body.index("openStream(")
    espera = load_body.index("await fetchSnapshot(")
    assert abre < espera, "openStream() tiene que ir antes del await del histórico"


def test_el_fallo_del_historico_no_escribe_en_el_banner_de_la_conexion(load_body: str) -> None:
    assert "paintHistory(" in load_body
    assert "$('banner')" not in load_body, "`#banner` es de paintLive; el histórico tiene el suyo"


def test_el_aviso_del_historico_tiene_su_propio_hueco() -> None:
    assert 'id="banner-hist"' in INDEX.read_text(encoding="utf-8")
    assert "#banner-hist" in (WEB / "src" / "style.css").read_text(encoding="utf-8")


def test_el_snapshot_no_pisa_un_precio_ya_recibido_en_vivo(load_body: str) -> None:
    """El tick en vivo puede llegar antes que el histórico: la vela cerrada no lo sustituye."""
    assert re.search(r"if \(last && lastClose === null\) paintPrice\(last\)", load_body)


def test_cambiar_de_simbolo_no_deja_dos_sockets(load_body: str) -> None:
    """`load()` cierra el anterior antes de abrir el suyo, y lo primero es cerrar."""
    assert load_body.index("stream?.close()") < load_body.index("openStream(")
    assert load_body.count("openStream(") == 1


def test_el_estado_de_la_conexion_no_depende_del_snapshot(load_body: str) -> None:
    """`link` solo lo toca el callback del socket (y el arranque); nunca el camino del histórico."""
    asignaciones = re.findall(r"\blink = (\w+)", load_body)
    assert asignaciones == ["false", "up"], asignaciones
