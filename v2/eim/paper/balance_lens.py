"""Las dos lentes del balance del panel (T195): la oficial manda; «todo lo calculado» aparte.

Antes de T195 el balance superior del bróker simulado se calculaba sobre la VISTA recalculada desde
todos los contextos guardados: operaciones reconstruidas por backtest, `retro`, contextos
importados de otro equipo y la misma idea repetida en cada perfil. En la portátil, el 2026-11-18,
mostraba «Todo 1 620» (1 500 reconstruidas y 120 vividas, neto −9 890 USDT) mientras el universo
oficial de T144 contaba 87. Y publicaba acierto, acierto necesario y neto sobre esa mezcla.

Ahora:
- `balance` = universo OFICIAL (T144, `accounting.balance_trades` → `universe.result_rows`): lo
  vivido, con peso, sin `retro`, de cualquier equipo (libro central, T196). Es lo que el panel
  muestra por defecto.
- `balance_all` = la vista de siempre, con su desglose por origen (`vivo`/`backtest`) en cada
  ventana. Se puede mirar, pero lleva su etiqueta y no es cifra de resultado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from eim.paper import accounting, universe
from eim.paper.balance import DAY_MS, WINDOWS, balance

OFFICIAL_LABEL = ("Oficial (T144): operaciones vividas, con peso y sin `retro`, de todos los "
                  "equipos; una vela = una operación")
ALL_LABEL = ("Todo lo calculado: la vista recalculada desde todos los contextos guardados "
             "(incluye reconstruidas por backtest y `retro`). No es cifra de resultado.")


def _by_origin(trades_by_profile: Mapping[str, Sequence[dict]], now: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, _label, days in WINDOWS:
        since = None if days is None else now - days * DAY_MS
        n: dict[str, int] = {}
        for ts in trades_by_profile.values():
            for t in ts:
                if since is None or t["exit_t"] >= since:
                    o = str(t.get("origin") or "desconocido")
                    n[o] = n.get(o, 0) + 1
        out[key] = dict(sorted(n.items()))
    return out


def payload(pstore, symbol: str, view_books: Mapping[str, object], names: Mapping[str, str],
            now: int, timeframes: Sequence[str]) -> dict:
    """`balance` (oficial), `balance_all` (vista) y `balance_lens` (qué es cada una)."""
    view = {pid: list(b.trades) for pid, b in view_books.items()}
    calc = balance(view, names, now, timeframes)
    for key, n in _by_origin(view, now).items():
        calc[key]["by_origin"] = n
    lens = {"default": "oficial", "universe": universe.declaration()["universe"],
            "labels": {"oficial": OFFICIAL_LABEL, "todo": ALL_LABEL}, "error": ""}
    try:
        official = balance(accounting.balance_trades(pstore, symbol), names, now, timeframes)
    except Exception as exc:  # noqa: BLE001 - un libro ilegible no tumba el panel
        lens["error"] = f"{type(exc).__name__}: {exc}"
        official = None
    return {"balance": official, "balance_all": calc, "balance_lens": lens}
