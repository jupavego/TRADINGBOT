"""CLI de la biblioteca digital (T151–T158), desde `v2/`:

    python -m eim.library.digital verify [--refresh]        # seed.json → catalog.json (registros)
    python -m eim.library.digital list [--category A] [--availability texto_completo]
    python -m eim.library.digital search "consulta" [--author X] [--strategy ind_donchian]
    python -m eim.library.digital show ID
    python -m eim.library.digital research [--full] [--only ID ...]   # fichas → cards.json
    python -m eim.library.digital consensus CONCEPTO | --contradictions
    python -m eim.library.digital contrast --side 1 --strategy ind_donchian@1h [--trend 1]
    python -m eim.library.digital learn [--api http://127.0.0.1:8000]  # libro fijo → trazas

Sin conexión, `verify` y `research` siguen con la caché (`data/library/digital/cache/`). Lo
descargado es dato, nunca instrucción. Nada de esto opera ni cambia perfiles.
"""

from __future__ import annotations

import argparse
import json
import sys

from eim.data.library_digital import (
    DigitalPaths,
    Http,
    append_traces,
    load_cards,
    load_catalog,
    load_kb,
    load_seed,
    save_cards,
    save_catalog,
    verify,
)
from eim.library.digital import catalog as cat
from eim.library.digital.consensus import consensus, contradictions
from eim.library.digital.contrast import TradeContext, contrast
from eim.library.digital.learning import evaluate


def _print(d: object) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=1))


def _verify(a: argparse.Namespace, paths: DigitalPaths) -> int:
    http, refs = Http(), []
    for s in load_seed():
        r = verify(s, paths, http, refresh=a.refresh)
        refs.append(r)
        v = r.verified
        print(("OK " if r.ok else "XX ") + f"{r.id}: " + (r.problem or
              f"{v.access}/{v.availability}" if v else r.problem or ""))
    save_catalog(refs)
    bad = [r.id for r in refs if not r.ok]
    print(f"{len(refs) - len(bad)}/{len(refs)} verificadas" + (f"; sin verificar: {bad}"
                                                              if bad else ""))
    return 0


def _learn(api: str, paths: DigitalPaths) -> int:
    import httpx

    from eim.paper.universe import counts_as_result
    r = httpx.get(f"{api}/v2/paper/ledger", params={"scope": "perfil", "limit": 20000},
                  timeout=60)
    r.raise_for_status()
    rows = [x for x in r.json()["rows"] if counts_as_result(x).counts]
    res = evaluate(rows, load_kb())
    added = append_traces(paths, res.pop("traces"))
    _print({**res, "traces_added": added})
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.library.digital")
    ap.add_argument("cmd", choices=["verify", "list", "search", "show", "research",
                                    "consensus", "contrast", "learn"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--full", action="store_true", help="descargar texto completo legal")
    ap.add_argument("--only", nargs="*")
    for f in ("category", "availability", "author", "title", "concept", "strategy", "regime"):
        ap.add_argument(f"--{f}", default="")
    ap.add_argument("--side", type=int, default=1)
    ap.add_argument("--trend", type=int, default=0)
    ap.add_argument("--contradictions", action="store_true")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    a = ap.parse_args(argv)
    paths = DigitalPaths.from_env()
    if a.cmd == "verify":
        return _verify(a, paths)
    if a.cmd == "research":
        from eim.data.library_research import research
        cards = load_cards()
        cards.update(research(load_catalog(), paths, Http(), full=a.full,
                              only=set(a.only) if a.only else None))
        save_cards(cards)
        return 0
    if a.cmd == "learn":
        return _learn(a.api, paths)
    refs = load_catalog()
    if a.cmd in ("list", "search"):
        hits = cat.search(refs, " ".join(a.args), a.author, a.title, a.category,
                          a.availability, a.concept, a.strategy)
        for r in hits:
            v = cat.view(r)
            print(f"[{v['category']}] {r.id}: {v['title'][:70]} ({v['year']}) · {v['access']}"
                  f"/{v['availability']}")
        print(f"{len(hits)} obras")
        return 0 if hits else 1
    if a.cmd == "show":
        r = next((x for x in refs if x.id == (a.args or [""])[0]), None)
        if r is None:
            print("obra inexistente")
            return 1
        _print(cat.view(r, load_cards().get(r.id)))
        return 0
    kb = load_kb()
    if a.cmd == "consensus":
        _print(contradictions(kb) if a.contradictions else consensus(kb, a.args[0]))
        return 0
    _print(contrast(kb, TradeContext(side=a.side, strategy=a.strategy, trend=a.trend,
                                     regime=a.regime or None)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
