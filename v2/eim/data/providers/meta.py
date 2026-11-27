"""Ficha de cada fuente de datos (T90): cobertura, retraso, límites y licencia.

Regla de CLAUDE.md: «nunca presentar datos asumidos como reales; toda cifra expone su
`source` y su cobertura real». Hasta T89 el almacén guardaba solo el nombre de la fuente;
desde T90 cada serie puede llevar al lado lo que esa fuente permite hacer con ella.

Las fichas copian lo que la ◆ de T88 dejó escrito (`PLAN/notas/T88_decisiones.md` §2-§3), sin
mejorarlo: si allí pone «no verificado», aquí también; la de Deribit copia la nota de términos de
la ◆ de T213 (`PLAN/notas/T213_terminos.md`) con el mismo criterio. El nivel de cobertura es el de
`TradableLevel` del registro (1 investigación · 2 operativa · 3 ejecución); hoy ninguna fuente
es de nivel 3 y el alcance aprobado es solo análisis.

Una fuente desconocida **no** sube de nivel por defecto: `lookup` la devuelve como nivel 1 y
«licencia no declarada», que es lo único honesto que se puede decir de ella.
"""

from __future__ import annotations

from pydantic import field_validator

from eim.core.market import Frozen

UNKNOWN_LICENSE = "no declarada"


class SourceMeta(Frozen):
    """Lo que una fuente declara de sí misma; viaja con cada serie que escribe."""

    name: str
    coverage: int                   # 1 investigación · 2 operativa · 3 ejecución (◆ T88 §2)
    license: str
    delay_ms: int | None = 0        # retraso de publicación; None = desconocido
    rate_limit_per_min: int | None = None   # peticiones por minuto; None = sin cifra publicada
    attribution: str = ""           # texto de atribución obligatorio, si lo hay
    notes: str = ""

    @field_validator("coverage")
    @classmethod
    def _level(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("coverage es 1, 2 o 3 (niveles de la ◆ de T88 §2)")
        return v

    def as_dict(self) -> dict:
        return self.model_dump()


BINANCE_FUTURES = SourceMeta(
    name="binance-futures", coverage=2, delay_ms=0, rate_limit_per_min=2400,
    license=("Términos de datos de la API REST: NO VERIFICADOS (◆ T88 §5.2); en uso desde T03 "
             "sin licencia nueva"),
    notes="2 400 de peso por minuto e IP; solo velas cerradas")
BINANCE_VISION = SourceMeta(
    name="binance-vision", coverage=1, delay_ms=86_400_000,
    license="CC BY-NC-SA 4.0 (v1.0, 2026-08-26): prohíbe ejecución en real y distribuir señales",
    attribution="Binance Vision, CC BY-NC-SA 4.0",
    notes="Solo investigación personal: el día que haya dinero real no puede estar en la cadena")
FRED = SourceMeta(
    name="fred", coverage=2, delay_ms=None, rate_limit_per_min=None,
    license="Clave gratuita; series de terceros con copyright solo para uso personal",
    attribution=("This product uses the FRED® API but is not endorsed or certified by the "
                 "Federal Reserve Bank of St. Louis."))
US_TREASURY = SourceMeta(
    name="us-treasury", coverage=2, delay_ms=None,
    license="Reutilización declarada sin restricción (no nombra licencia)",
    notes="Curva par diaria; se actualiza hacia las 15:30 ET")
ECB = SourceMeta(
    name="ecb", coverage=2, delay_ms=None,
    license="Uso libre citando al BCE como fuente", attribution="Fuente: Banco Central Europeo")
FRANKFURTER = SourceMeta(
    name="frankfurter", coverage=2, delay_ms=None,
    license="Código MIT; datos del BCE con su misma condición de cita",
    attribution="Fuente: Banco Central Europeo (vía Frankfurter)")
YAHOO = SourceMeta(
    name="yahoo", coverage=1, delay_ms=None,
    license=("SIN licencia de datos: los Términos de Yahoo prohíben la recolección automatizada "
             "y crear bases de datos (◆ T88 §3)"),
    notes="Solo investigación; descartado para T90+ (sustitución en BACKLOG)")
#: T213 (◆ del usuario, 2026-11-27): términos leídos en `PLAN/notas/T213_terminos.md`. Nivel 1
#: y no 2: el límite por IP no tiene cifra publicada y la cl. 27.1(i) queda ambigua.
DERIBIT = SourceMeta(
    name="deribit", coverage=1, delay_ms=0, rate_limit_per_min=None,
    license=("Términos de Deribit FZE (26-01-2026), cl. 2.10: datos de mercado y derivados solo "
             "para uso personal; prohibido publicar, reenviar o redistribuir sin aprobación "
             "escrita. Cl. 27.1(i) (recolección automatizada) ambigua para la API pública: "
             "aprobada por el usuario a nivel 1 (◆ T213, 2026-11-27). Términos de DRB Panama "
             "NO VERIFICADOS"),
    notes=("API pública sin clave (DVOL de T165 y cadenas de opciones de T213); límite por IP "
           "sin cifra publicada; el interés abierto llega con 8 h de retraso; nada sale del "
           "proyecto"))

#: Catálogo por nombre canónico.
SOURCES: dict[str, SourceMeta] = {m.name: m for m in (
    BINANCE_FUTURES, BINANCE_VISION, FRED, US_TREASURY, ECB, FRANKFURTER, YAHOO, DERIBIT)}

#: Cómo se escribe la fuente en `meta.json` de series antiguas → nombre canónico. Se compara
#: en minúsculas y por prefijo, en este orden (lo más específico primero).
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("binance-vision", "binance-vision"), ("binance vision", "binance-vision"),
    ("data.binance.vision", "binance-vision"),
    ("binance-futures", "binance-futures"), ("binance futures", "binance-futures"),
    ("yahoo", "yahoo"), ("fred", "fred"), ("alfred", "fred"),
    ("us-treasury", "us-treasury"), ("frankfurter", "frankfurter"), ("ecb", "ecb"),
    ("bce", "ecb"), ("deribit", "deribit"),   # `deribit-dvol` (T165) y `deribit-options` (T213)
)


def lookup(source: str | None) -> SourceMeta:
    """Ficha de una fuente por el nombre con que se guardó. Desconocida → nivel 1, sin licencia
    declarada y retraso desconocido (nunca se le supone más de lo que se sabe)."""
    s = (source or "").strip().lower()
    for prefix, canon in _PREFIXES:
        if s.startswith(prefix):
            return SOURCES[canon]
    return SourceMeta(name=source or "desconocida", coverage=1, license=UNKNOWN_LICENSE,
                      delay_ms=None)


def meta_of(provider: object) -> SourceMeta:
    """La ficha que declara el proveedor (`provider.meta`) o, si no declara, la del catálogo
    por su nombre."""
    meta = getattr(provider, "meta", None)
    if isinstance(meta, SourceMeta):
        return meta
    return lookup(getattr(provider, "name", None))
