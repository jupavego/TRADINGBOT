"""Escaneo en vivo (solo lectura, REST público): `python -m eim.arbitrage.cli [--json]`.

Orquesta: carga en `eim/data/arb_market.py` (I/O) → `scan_all` (puro). Modo ANÁLISIS: no
envía órdenes.
"""

from __future__ import annotations

import argparse
import json
import sys

from eim.arbitrage.params import ArbParams
from eim.arbitrage.scan import ArbResult, scan_all
from eim.core import CostModel
from eim.data.arb_market import load_arb_market
from eim.data.providers.binance_arb import BinanceArbData


def _borrow(items: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for it in items:
        asset, _, rate = it.partition("=")
        out[asset.upper()] = float(rate)
    return out


def render(res: ArbResult) -> str:
    lines = [f"Arbitraje Binance · modo ANÁLISIS · asof {res.asof} · comisiones: "
             f"{res.cost_model.source}"]
    for s in res.scans:
        lines.append(f"- {s.strategy}: {s.status}, {len(s.opportunities)} valoradas"
                     + (f"; falta: {'; '.join(s.missing)}" if s.missing else ""))
        lines += [f"    aviso: {w}" for w in s.warnings]
    lines.append("Seleccionadas (pb/día ajustados por riesgo):")
    for r in res.selection.selected:
        o = r.opportunity
        lines.append(f"  {r.score:8.2f}  {o.strategy:14s} {o.asset:22s} {o.variant:38s} "
                     f"neto {o.net_edge:+9.2f} ({o.net_bps:+.1f} pb) bruto {o.gross_edge:+.2f}")
    lines.append("Descartadas:")
    for r in res.selection.rejected:
        o, c = r.opportunity, r.opportunity.costs
        lines.append(f"  {o.strategy:14s} {o.asset:22s} {o.variant:38s} bruto "
                     f"{o.gross_edge:+8.2f} com {c.fees:6.2f} desl {c.slippage:6.2f} fund "
                     f"{c.funding:+7.2f} prést {c.borrow:5.2f} → neto {o.net_edge:+8.2f} "
                     f"({o.net_bps:+.1f} pb) · {r.reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notional", type=float, default=10_000.0)
    ap.add_argument("--spot-vip", type=int, default=0)
    ap.add_argument("--futures-vip", type=int, default=0)
    ap.add_argument("--bnb", action="store_true", help="paga comisiones con BNB")
    ap.add_argument("--borrow", nargs="*", default=[], metavar="ACTIVO=TASA",
                    help="interés anual de préstamo spot (fracción), p. ej. BTC=0.03")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows (cp1252)
    p = ArbParams(notional_usd=a.notional)
    cm = CostModel(spot_vip=a.spot_vip, futures_vip=a.futures_vip, bnb_discount=a.bnb)
    mkt = load_arb_market(BinanceArbData(), assets=p.assets, borrow_apr=_borrow(a.borrow))
    res = scan_all(mkt, cm, p)
    if a.json:
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=1))
    else:
        print(render(res))
        if mkt.errors:
            print("Errores de carga:", json.dumps(mkt.errors, ensure_ascii=False))


if __name__ == "__main__":
    main()
