"""Captura HFT (T78): tablas de `micro_hft/` y paso de mensajes de Binance a filas. Puro.

Cada fila empieza con la misma cabecera: `recv_ns` (hora UTC de recepción en ns, de un reloj
monotónico de alta resolución anclado al de pared; ver `hft_clock`), `mono_ns` (ese reloj
monotónico), `run` (`recv_ns` del arranque del proceso) y `seq` (orden de proceso dentro de la
corrida: orden total con el que se reproduce el libro). Los eventos de mercado guardan además los
relojes del exchange: `e_ms` (`E`, hora del evento) y `t_ms` (`T`, hora de la transacción; −1 si el
flujo no la trae). Los niveles del libro van como listas paralelas de precio y cantidad.

Tablas: `depth` (todos los diffs de `depth@100ms`, también los que llegan sin libro), `bbo`
(`bookTicker`), `trades` (`aggTrade`), `mark` (`markPrice@1s`: marca, índice, funding), `liq`
(`forceOrder`), `snap` (snapshots REST), `book` (libro completo del recolector en cada arranque,
cambio de hora y reconstrucción: punto de partida exacto del conversor), `checks` (comparación
con el snapshot REST), `gaps` (tramos marcados) y `clock` (re-anclajes del reloj local).
"""

from __future__ import annotations

AREA = "micro_hft"
HOUR_NS = 3_600_000_000_000
HEAD = (("recv_ns", "BIGINT"), ("mono_ns", "BIGINT"), ("run", "BIGINT"), ("seq", "BIGINT"))
_LEVELS = (("bp", "DOUBLE[]"), ("bq", "DOUBLE[]"), ("ap", "DOUBLE[]"), ("aq", "DOUBLE[]"))
_EXCH = (("e_ms", "BIGINT"), ("t_ms", "BIGINT"))

COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "depth": (*_EXCH, ("first_id", "BIGINT"), ("last_id", "BIGINT"), ("prev_id", "BIGINT"),
              *_LEVELS),
    "bbo": (*_EXCH, ("upd_id", "BIGINT"), ("bid_p", "DOUBLE"), ("bid_q", "DOUBLE"),
            ("ask_p", "DOUBLE"), ("ask_q", "DOUBLE")),
    "trades": (*_EXCH, ("agg_id", "BIGINT"), ("first_trade", "BIGINT"), ("last_trade", "BIGINT"),
               ("p", "DOUBLE"), ("q", "DOUBLE"), ("maker", "BOOLEAN")),  # maker = vende el agresor
    "mark": (("e_ms", "BIGINT"), ("mark_p", "DOUBLE"), ("index_p", "DOUBLE"),
             ("settle_p", "DOUBLE"), ("funding", "DOUBLE"), ("next_funding_ms", "BIGINT")),
    "liq": (*_EXCH, ("side", "VARCHAR"), ("p", "DOUBLE"), ("avg_p", "DOUBLE"), ("q", "DOUBLE"),
            ("filled_q", "DOUBLE"), ("status", "VARCHAR")),
    "snap": (("req_ns", "BIGINT"), *_EXCH, ("update_id", "BIGINT"), ("purpose", "VARCHAR"),
             *_LEVELS),
    "book": (("purpose", "VARCHAR"), ("last_id", "BIGINT"), ("last_u", "BIGINT"),
             ("synced", "BOOLEAN"), *_LEVELS),
    "checks": (("snap_id", "BIGINT"), ("at_id", "BIGINT"), ("comparable", "BOOLEAN"),
               ("match", "BOOLEAN"), ("n_diff", "INTEGER"), ("book_hash", "VARCHAR"),
               ("detail", "VARCHAR")),
    "gaps": (("stream", "VARCHAR"), ("cause", "VARCHAR"), ("start_ns", "BIGINT"),
             ("end_ns", "BIGINT"), ("n", "BIGINT"), ("detail", "VARCHAR")),
    "clock": (("kind", "VARCHAR"), ("jump_ns", "BIGINT"), ("wall_ns", "BIGINT")),
}
KINDS = tuple(COLUMNS)
MARKET = {"depthUpdate": "depth", "bookTicker": "bbo", "aggTrade": "trades",
          "markPriceUpdate": "mark", "forceOrder": "liq"}
# causas de un tramo marcado (el orden fija su código en los eventos del simulador)
CAUSES = ("secuencia", "sin_libro", "silencio", "desconexion", "cola_llena", "divergencia",
          "ids_trades")


def columns(kind: str) -> list[str]:
    return [n for n, _ in HEAD + COLUMNS[kind]]


def ddl(kind: str) -> str:
    return ", ".join(f"{n} {t}" for n, t in HEAD + COLUMNS[kind])


def levels(rows) -> tuple[list[float], list[float]]:
    """`[["67000.1", "1.5"], ...]` → (precios, cantidades) como float."""
    return [float(p) for p, _ in rows], [float(q) for _, q in rows]


def kind_of(d: dict, symbol: str) -> str | None:
    """Tipo de tabla del mensaje, o None si no es de este símbolo o no se guarda."""
    kind = MARKET.get(d.get("e", ""))
    if kind is None:
        return None
    if kind == "liq" and not isinstance(d.get("o"), dict):
        return None
    sym = d["o"].get("s") if kind == "liq" else d.get("s")
    return kind if sym in (None, symbol) else None


def _num(x, default: float = float("nan")) -> float:
    return float(x) if x not in (None, "") else default


def market_row(kind: str, d: dict, head: tuple) -> tuple:
    """Fila de `kind` para el mensaje `d` (ya decodificado) con la cabecera `head`."""
    if kind == "depth":
        bp, bq = levels(d["b"])
        ap, aq = levels(d["a"])
        return (*head, int(d["E"]), int(d.get("T", -1)), int(d["U"]), int(d["u"]), int(d["pu"]),
                bp, bq, ap, aq)
    if kind == "bbo":
        return (*head, int(d.get("E", -1)), int(d.get("T", -1)), int(d["u"]), float(d["b"]),
                float(d["B"]), float(d["a"]), float(d["A"]))
    if kind == "trades":
        return (*head, int(d["E"]), int(d["T"]), int(d["a"]), int(d.get("f", -1)),
                int(d.get("l", -1)), float(d["p"]), float(d["q"]), bool(d["m"]))
    if kind == "mark":
        return (*head, int(d["E"]), float(d["p"]), _num(d.get("i")), _num(d.get("P")),
                _num(d.get("r")), int(d.get("T") or -1))
    o = d["o"]                                                     # liq (`forceOrder`)
    return (*head, int(d["E"]), int(o.get("T", -1)), str(o["S"]), float(o["p"]),
            _num(o.get("ap"), 0.0), float(o["q"]), _num(o.get("z"), 0.0), str(o.get("X", "")))
