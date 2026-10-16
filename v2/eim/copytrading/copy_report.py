"""Informe de la copia simulada (puro, T42) → `reports/copytrading_sim.md`.

Separa el rendimiento APARENTE (el del líder, escalado a la subcuenta) del COPIABLE (el que
obtiene la subcuenta con latencia, precio del seguidor, comisiones, funding, topes y vetos),
con la diferencia repartida en causas. Toda cifra dice de qué fuente sale.
"""

from __future__ import annotations

import time

from eim.copytrading.copy_attrib import CAUSES, Attribution
from eim.copytrading.copy_params import CopyParams
from eim.core.market import Frozen

CAUSE_TEXT = {"latencia": "latencia (el precio se movió antes de nuestra orden)",
              "diferencial": "diferencial (cruzar el libro: ask/bid vs medio)",
              "comisiones": "comisiones (tomador propio vs las del líder)",
              "funding": "funding (propio vs el del líder a nuestro tamaño)",
              "no_copiadas": "viajes no copiados",
              "tamano": "tamaño (topes, redondeo, tope de riesgo)",
              "resto": "resto (aumentos omitidos, stops, redondeo a mitad)"}
SRC_TEXT = {"bbo": "bid/ask grabado (WS `bbo`)", "allMids": "precio medio `allMids` + "
            "medio diferencial supuesto", "vela_1m": "cierre de vela 1 min + deslizamiento T25 "
            "(supuesto)", "marca": "marca vigente + medio diferencial (supuesto)",
            "lider": "precio del líder + deslizamiento base (supuesto)"}


class LeaderSim(Frozen):
    leader_id: str
    label: str = ""
    status: str
    measure: bool
    start: int
    end: int
    attribution: Attribution
    account: dict
    price_src: dict[str, int] = {}
    latency: dict[str, float | None] = {}  # señales vistas en vivo (ms)
    funding_missing: int = 0
    warnings: list[str] = []


def _u(x: float | None, d: int = 2) -> str:
    return "—" if x is None else f"{x:+,.{d}f}".replace(",", " ").replace(".", ",")


def _n(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _pct(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{x * 100:+.{d}f} %".replace(".", ",")


def _utc(t: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t / 1000))


def _short(s: LeaderSim) -> str:
    a = s.leader_id.split(":", 1)[-1]
    return f"{s.label} ({a[:6]}…{a[-4:]})" if s.label else f"{a[:6]}…{a[-4:]}"


def _leader_rows(sims: list[LeaderSim]) -> list[str]:
    out = ["| Líder | Estado T41 | Ventana | Viajes líder (cerrados) | Copiados | No copiados | "
           "Aparente (USD) | Copiable (USD) | pb líder | pb seguidor | Capital final | "
           "Caída máx. |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sims:
        a, acc = s.attribution, s.account
        hours = (s.end - s.start) / 3_600_000
        out.append(
            f"| {_short(s)} | {s.status} | {_n(hours)} h | {a.trips} | {a.copied} | "
            f"{a.skipped} | {_u(a.apparent)} | {_u(a.follower)} | {_n(a.leader_bps)} | "
            f"{_n(a.follower_bps)} | {_n(acc['equity'], 2)} ({_pct(acc['ret'], 2)}) | "
            f"{_pct(acc['max_dd'])} |")
    return out


def _causes(sims: list[LeaderSim]) -> list[str]:
    tot = {k: sum(s.attribution.causes.get(k, 0.0) for s in sims) for k in CAUSES}
    app = sum(s.attribution.apparent for s in sims)
    fol = sum(s.attribution.follower for s in sims)
    out = [f"Aparente total **{_u(app)} USD** → copiable **{_u(fol)} USD** "
           f"(diferencia {_u(fol - app)} USD = suma de causas):", "",
           "| Causa | Aporte (USD) | " + " | ".join(_short(s) for s in sims) + " |",
           "|---|---|" + "---|" * len(sims)]
    for k in CAUSES:
        out.append(f"| {CAUSE_TEXT[k]} | {_u(tot[k])} | " + " | ".join(
            _u(s.attribution.causes.get(k, 0.0)) for s in sims) + " |")
    skips: dict[str, list[float]] = {}
    for s in sims:
        for code, v in s.attribution.skipped_by.items():
            n = s.attribution.skipped_n.get(code, 0)
            cur = skips.setdefault(code, [0, 0.0])
            cur[0] += n
            cur[1] += v
    if skips:
        out += ["", "Viajes no copiados por motivo (n · aporte):", ""]
        out += [f"- `{code}`: {int(n)} viajes · {_u(v)} USD" for code, (n, v) in
                sorted(skips.items(), key=lambda kv: -kv[1][0])]
    return out


def _top_causes(sims: list[LeaderSim]) -> str:
    tot = {k: sum(s.attribution.causes.get(k, 0.0) for s in sims) for k in CAUSES}
    top = sorted(tot.items(), key=lambda kv: kv[1])[:3]
    return ("- La brecha viene sobre todo de: " +
            "; ".join(f"{CAUSE_TEXT[k]} {_u(v)} USD" for k, v in top if v < 0) + ".")


def _recon(sims: list[LeaderSim]) -> list[str]:
    def n(key: str) -> int:
        return sum(s.account.get("counts", {}).get(key, 0) for s in sims)
    return [f"- Reconciliaciones con la foto real del líder: {n('recon')}; con alguna diferencia "
            f"explicada (topes, mínimos, vetos, señales en camino): {n('recon_diff')}; con "
            f"diferencia **no explicada**: {n('recon_unexplained')}"
            + (" (aisladas: ninguna se repitió en la foto siguiente)"
               if n("recon_unexplained") and not n("pauses") else "")
            + f" → pausas: **{n('pauses')}**.",
            f"- Resincronizaciones por hueco de captura conocido (> 5 min sin confirmar el "
            f"flujo: equipo apagado, reinicios del servicio): {n('resyncs')}. Ejecuciones "
            f"llegadas tarde y anteriores a lo ya procesado (reenvío del WS antes que el relleno "
            f"REST): {n('stale')}, tratadas como historial."]


def _execution(sims: list[LeaderSim]) -> list[str]:
    src: dict[str, int] = {}
    for s in sims:
        for k, v in s.price_src.items():
            src[k] = src.get(k, 0) + v
    total = sum(src.values()) or 1
    out = ["Precio del seguidor por señal:", ""]
    out += [f"- {SRC_TEXT.get(k, k)}: {v} ({v / total:.0%})" for k, v in
            sorted(src.items(), key=lambda kv: -kv[1])]
    out += ["", "| Líder | Señales | Órdenes | Latencia señal p50 / p90 (ms) | Rechazos por "
            "motivo | Funding (USD) | Comisiones (USD) | Horas sin tasa |",
            "|---|---|---|---|---|---|---|---|"]
    for s in sims:
        acc, c = s.account, s.account.get("counts", {})
        rej = ", ".join(f"{k} {v}" for k, v in sorted(acc.get("rejects", {}).items(),
                                                       key=lambda kv: -kv[1])) or "—"
        out.append(f"| {_short(s)} | {c.get('signals', 0)} | {c.get('orders', 0)} | "
                   f"{_n(s.latency.get('p50'), 0)} / {_n(s.latency.get('p90'), 0)} | {rej} | "
                   f"{_u(acc['funding'])} | {_u(-acc['fees'])} | {s.funding_missing} |")
    return out


def _live(live: dict | None, now: int) -> list[str]:
    if not live:
        return ["Sin resumen en vivo (`data/leaders/copy_sim.json`): el servicio de líderes no "
                "corre con la copia activada (`EIM_COPY_SIM`)."]
    accs = live.get("accounts", [])
    age = (now - live["asof"]) / 1000
    started = min((a["started_t"] for a in accs), default=live["asof"])
    hours = (live["asof"] - started) / 3_600_000
    rec = sum(a["counts"].get("recon", 0) for a in accs)
    bad = sum(a["counts"].get("recon_unexplained", 0) for a in accs)
    pauses = [a for a in accs if a.get("paused")]
    last_bad = max((a.get("last_unexplained_t") or 0 for a in accs), default=0)
    clean = (f"sin diferencias no explicadas desde {_utc(last_bad)} "
             f"(**{_n((live['asof'] - last_bad) / 3_600_000)} h**)" if last_bad else
             "las acumuladas no tienen hora registrada (estado anterior al registro)" if bad
             else "ninguna diferencia no explicada en todo el seguimiento")
    out = [f"Modo **{live['mode']}** ({live.get('label', '')}); resumen de {_utc(live['asof'])} "
           f"(hace {_n(age, 0)} s). Subcuentas: {len(accs)}; seguimiento desde "
           f"{_utc(started)} (**{_n(hours)} h**). Reconciliaciones: {rec}; con diferencia no "
           f"explicada: {bad} (acumulado); {clean}; en pausa ahora: {len(pauses)}.", "",
           "| Líder | Capital | Resultado | Órdenes | Rechazos | Posiciones | Pausa |",
           "|---|---|---|---|---|---|---|"]
    for a in accs:
        a_id = a["leader_id"].split(":", 1)[-1]
        out.append(f"| {a.get('label') or a_id[:10]} | {_n(a['equity'], 2)} | "
                   f"{_u(a['pnl'])} | {a['counts'].get('orders', 0)} | "
                   f"{sum(a.get('rejects', {}).values())} | "
                   f"{sum(1 for x in a['positions'] if x['size'])} | {a.get('paused') or '—'} |")
    return out


def render(sims: list[LeaderSim], live: dict | None, p: CopyParams, risk_version: str,
           now: int, spec_source: str) -> str:
    approved = [s for s in sims if s.status == "approved"]
    measure = len(sims) - len(approved)
    app = sum(s.attribution.apparent for s in sims)
    fol = sum(s.attribution.follower for s in sims)
    l_bps = [s.attribution.leader_bps for s in sims if s.attribution.leader_bps is not None]
    f_bps = [s.attribution.follower_bps for s in sims if s.attribution.follower_bps is not None]
    out = [
        "# Copy trading — replicación simulada (T42)", "",
        f"Generado {_utc(now)} · modo **SIMULADO** (saldo virtual de {_n(p.initial_equity, 0)} "
        "USDC por líder; ninguna orden real ni de testnet) · *El rendimiento pasado no garantiza "
        "resultados futuros.*", "",
        "## Veredicto", "",
        f"- Líderes simulados: {len(sims)}; aprobados por el scorecard (T41): {len(approved)}. "
        + (f"**{measure} se simulan solo para medir** (ninguno debería copiarse hoy)."
           if measure else ""),
        f"- Rendimiento **aparente** (el del líder × proporción, viajes cerrados): {_u(app)} USD. "
        f"**Copiable** (subcuentas, mismos viajes): {_u(fol)} USD.",
        f"- Por unidad de nocional, en los viajes copiados: líder {', '.join(_n(x) for x in l_bps)}"
        f" pb · seguidor {', '.join(_n(x) for x in f_bps)} pb (por líder, mismo orden que la "
        "tabla).",
        _top_causes(sims),
        "- Muestra corta (horas, decenas de viajes): las cifras describen lo ocurrido, no "
        "estiman un edge; ninguna prueba de significancia aplica con este n.", "",
        "## Resultado por líder (reproducción del historial capturado)", ""]
    out += _leader_rows(sims)
    out += ["", "## Copiable vs aparente: causas de la diferencia", ""]
    out += _causes(sims)
    out += ["", "## Reconciliación de la reproducción", ""] + _recon(sims)
    out += ["", "## Ejecución simulada", ""]
    out += _execution(sims)
    warns = [f"- {_short(s)}: {w}" for s in sims for w in s.warnings]
    if warns:
        out += ["", "Avisos:", ""] + warns
    out += ["", "## Simulación en vivo (servicio de líderes)", ""]
    out += _live(live, now)
    out += ["", "## Método y supuestos", "",
            f"- Mismo motor en vivo y en la reproducción (`eim/copytrading/copy_engine.py`): "
            f"objetivo = posición del líder × capital asignado / cuenta del líder (fijada al "
            f"abrir cada viaje; cuenta de `portfolio`). Topes: {p.max_asset_frac:.0%} del capital "
            f"por moneda y {p.max_leader_frac:.0%} por líder; deslizamiento máximo "
            f"{p.max_slippage:.1%} frente a la entrada media del líder; mínimos del exchange de "
            f"`meta` ({spec_source}); lo abierto antes de seguirlo no se copia.",
            f"- Riesgo: cada orden que aumenta riesgo pasa por el motor T29 con `{risk_version}` "
            f"(stop de protección {p.stop_frac:.0%}, señal ≤ 30 s, flujo confirmado ≤ 2 min, "
            "pérdida diaria/semanal, enfriamiento, kill-switch propio por caída). Reducir o "
            "cerrar nunca se veta.",
            f"- La orden llega {p.exec_delay_ms} ms después de ver la ejecución del líder; "
            f"comisión de tomador {p.taker_fee:.3%} (Hyperliquid, nivel base); funding horario "
            "con la tasa real pagada por los líderes capturados; marcas y stops con velas de "
            "1 min de Hyperliquid.",
            "- Reconciliación con cada foto del líder: una diferencia sin motivo registrado en "
            f"{p.recon_confirm} comprobaciones seguidas pausa la subcuenta y avisa (nunca se "
            "opera para «cuadrar»).",
            "- Limitaciones: sin impacto del tamaño propio en el libro (subcuenta pequeña); "
            "stops evaluados al cierre de cada minuto; sin cotización grabada, el precio es "
            "un supuesto declarado arriba; una subcuenta por líder (sin compensar posiciones "
            "entre líderes: eso es el asignador de T46)."]
    return "\n".join(out) + "\n"
