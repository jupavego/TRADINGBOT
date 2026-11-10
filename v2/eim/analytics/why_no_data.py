"""¿Por qué esta esfera dice «sin datos»? Diagnóstico repetible contra la API local (T120).

Primer paso de la skill `eim-diagnose-agent`, igual en cualquier equipo: lista cada agente con su
estado y su motivo completo (el mismo que resume la esfera), el estado de los recolectores
(`health.LABELS`) y qué componentes están vivos, desde qué checkout y desde cuándo. Solo lectura;
solo habla con la API en 127.0.0.1.

    python -m eim.analytics.why_no_data --symbol BTCUSDT --tf 1h [--api http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def latest_per_agent(reports: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in reports:
        cur = out.get(r["agent_id"])
        if cur is None or r["asof"] > cur["asof"]:
            out[r["agent_id"]] = r
    return out


def agent_lines(agents: list[dict], reports: list[dict], micro: dict | None) -> list[str]:
    """Una línea por agente: estado, motivo (el primero que no sea un aviso fijo) y, si depende de
    un recolector que no captura, su estado (manda sobre el del agente, como en la esfera)."""
    last = latest_per_agent(reports)
    lines = []
    for a in sorted(agents, key=lambda x: (x["status"] == "ok", x["id"])):
        r = last.get(a["id"]) or {}
        why = " · ".join(r.get("warnings") or []) or "—"
        tag = ""
        if a["id"] == "microstructure" and micro and micro.get("state") != "capturando":
            tag = f" [recolector: {micro.get('label')} — {micro.get('reason')}]"
        lines.append(f"  {a['status']:<11} {a['id']:<15} {why}{tag}")
    return lines


def component_lines(health: dict) -> list[str]:
    out = [f"  API: checkout {health.get('checkout') or 'sin declarar (código anterior a T120)'}"]
    for c in health.get("components") or []:
        since = ("" if not c.get("started_at") else
                 time.strftime(" desde %Y-%m-%d %H:%M UTC", time.gmtime(c["started_at"] / 1000)))
        age = "nunca" if c.get("age_s") is None else f"latido hace {c['age_s']:.0f} s"
        out.append(f"  {'vivo ' if c.get('alive') else 'CAÍDO'} {c['name']}: {age}{since} · "
                   f"{c.get('checkout') or 'checkout sin declarar'}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):    # consola cp1252: un carácter raro no tumba el informe
        sys.stdout.reconfigure(errors="replace")
    q = {"symbol": a.symbol, "tf": a.tf}
    try:
        with httpx.Client(base_url=a.api, timeout=15.0) as c:
            agents = c.get("/v2/agents", params=q).json()
            reports = c.get("/v2/reports", params={**q, "limit": 400}).json()
            micro = c.get("/v2/micro/status", params={"symbol": a.symbol}).json()
            health = c.get("/v2/health").json()
    except httpx.HTTPError as e:
        print(f"La API no responde en {a.api} ({type(e).__name__}): sin ella no hay esferas. "
              "Ver RUNBOOK §16.")
        return 2
    print(f"Agentes {a.symbol} {a.tf} (estado · id · motivo):")
    print("\n".join(agent_lines(agents, reports, micro)))
    print(f"Recolector de microestructura: {micro.get('label', micro.get('state'))} — "
          f"{micro.get('reason')}")
    print("Componentes:")
    print("\n".join(component_lines(health)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
