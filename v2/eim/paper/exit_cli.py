"""CLI de la calidad de las salidas (T130), desde `v2/`:

    python -m eim.paper salidas [--symbol BTCUSDT]

Lee `GET /v2/paper/exits` de la API en marcha (solo lectura) e imprime, por perfil, lo que decide
si la salida destruye la ventaja: ganancia y pérdida media, acierto real y de equilibrio, costo en
R, E[R] antes y después de costos, y el emparejado con la sombra (misma idea, salida A).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from eim.data.local_api import DEFAULT_API
from eim.data.timeframes import SYMBOLS


def add_parser(sub) -> None:
    sp = sub.add_parser("salidas", help="calidad de la salida por perfil y A/B con la sombra")
    sp.add_argument("--symbol", default="BTCUSDT", choices=SYMBOLS)
    sp.add_argument("--api", default=DEFAULT_API)
    sp.add_argument("--json", action="store_true", help="la respuesta tal cual")


def _f(x: float | None, fmt: str) -> str:
    return "—" if x is None else format(x, fmt)


def render(out: dict) -> list[str]:
    lines = [f"Modo: {out['mode']} · {out['symbol']} · instantánea {out.get('snapshot') or '—'}"]
    for pid, q in out["profiles"].items():
        lines.append(
            f"{pid:<12} ops {q['n']:>4}  acierto {_f(q['win_rate'], '.1%')} (equilibrio "
            f"{_f(q['breakeven_win_rate'], '.1%')})  ganadora {_f(q['avg_win_r'], '+.3f')} R  "
            f"perdedora {_f(q['avg_loss_r'], '+.3f')} R  PF {_f(q['pf'], '.2f')}")
        lines.append(
            f"{'':<12} E[R] {_f(q['expectancy_r'], '+.3f')} (bruto "
            f"{_f(q['gross_expectancy_r'], '+.3f')})  costo {_f(q['cost_mean_r'], '.3f')} R  "
            f"costos/bruto ganado {_f(q['costs_vs_gross_won'], '.0%')}")
        p = q.get("vs_shadow")
        if p:
            lines.append(
                f"{'':<12} vs sombra: {p['n']} pares, perfil {_f(p['book_r'], '+.3f')} R frente a "
                f"{_f(p['shadow_r'], '+.3f')} R (Δ {_f(p['delta_r'], '+.3f')}); salidas de la "
                f"sombra {p['shadow_exits']}")
            for key, label in (("when_shadow_tp", "la sombra llegó al TP"),
                               ("when_shadow_sl", "la sombra perdió por SL")):
                s = p.get(key)
                if s:
                    lines.append(f"{'':<14}{label} ({s['n']}): perfil {_f(s['book_r'], '+.3f')}"
                                 f" R, sombra {_f(s['shadow_r'], '+.3f')} R")
    lines.append("Nota: varios perfiles comparten ideas; sus operaciones no son independientes.")
    return lines


def run(a: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen(f"{a.api}/v2/paper/exits?symbol={a.symbol}",  # noqa: S310
                                    timeout=180) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        print(f"la API respondió {exc.code}: {exc.read().decode('utf-8', 'replace')}",
              file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"API no disponible ({exc}); arráncala o reintenta", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1) if a.json else "\n".join(render(out)))
    return 0
