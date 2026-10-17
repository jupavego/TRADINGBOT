"""`reports/arbitrage_edge.md` (T43): rentabilidad neta por estrategia, distribución, peor
caso, capital mínimo, sensibilidad, significancia, oportunidades reales y veredicto."""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.evaluate import STRATS
from eim.arbitrage.sim.frame import ArbHistory
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.report_extra import calibration, capital, triangular
from eim.arbitrage.sim.report_fmt import (
    NAMES,
    STATS_HEAD,
    bps,
    breakdown,
    brief_row,
    ci,
    day,
    num,
    pct,
    stats_row,
    table,
)
from eim.core import CostModel


def render(res: dict, hist: ArbHistory, cm: CostModel, p: ArbParams, sp: SimParams,
           generated: int) -> str:
    L: list[str] = [
        "# Arbitraje en Binance: ¿deja dinero neto? (T43)", "",
        f"**Modo: ANÁLISIS** — simulación histórica; no se envió ninguna orden. Generado "
        f"{day(generated)} (UTC). Período de decisiones: {day((res['period'] or [None])[0])} → "
        f"{day((res['period'] or [None, None])[1])} ({res['decisions']} decisiones cada "
        f"{sp.decision_every_h} h, {sp.decision_offset_h} h antes de cada liquidación de "
        "funding). Las cifras son netas de comisiones, deslizamiento por profundidad, funding, "
        "rebalanceo, liquidaciones y costo esperado de pata incompleta.", "",
        "Cómo se obtuvo: en cada decisión se reconstruye la fotografía que habría visto el "
        "escáner (T38) y se valora y selecciona con **el mismo código del motor** "
        "(`scan_*` + `select`); cada oportunidad se simula después vela a vela hasta su salida "
        "(`eim/arbitrage/sim/`). Política: una posición a la vez por estrategia y activo.", ""]
    L += _verdicts(res, sp)
    L += _data(hist, res)
    L += _assumptions(cm, p, sp)
    L += _strategies(res)
    L += triangular(res)
    L += _legging(res, sp)
    L += _sensitivity(res)
    L += _opportunities(res)
    L += capital(res, p)
    L += calibration(res)
    return "\n".join(L) + "\n"


def _verdicts(res: dict, sp: SimParams) -> list[str]:
    rows = []
    for s in (*STRATS, "triangular"):
        label, why = res["verdicts"][s]
        st = _main_stats(res, s)
        rows.append([NAMES[s], f"**{label}**", pct(st.get("apr_period")) if st else "—",
                     pct(st.get("last_year_apr")) if st else "—",
                     bps(st.get("mean_bps")) if st else "—",
                     ci(st.get("ci95_mean_bps")) if st else "—", str(st.get("n", 0)) if st
                     else "—", bps(st.get("worst_bps")) if st else "—", "; ".join(why)])
    return ["## Veredicto (caso base: VIP 0, sin BNB, 10 000 USD por operación)", "",
            *table(["Estrategia", "Veredicto", "Anual neto (período)", "Últimos 12 meses",
                    "Neto medio/op", "IC95 %", "Operaciones", "Peor op.", "Motivos"], rows), "",
            f"Reglas: *No viable* = el selector no toma nada o el neto medio ≤ 0; *Viable* = "
            f"neto medio > 0 con IC95 % > 0, anual del período y de los últimos 12 meses ≥ "
            f"{sp.hurdle_apr:.0%} (umbral de referencia **supuesto**, no un dato de mercado), "
            "sin liquidaciones y ≥ 10 operaciones; *Marginal* = el resto. El carry se juzga en "
            "su mejor tenencia; la base, con sus variantes no desactivadas. Anual = neto / "
            "capital comprometido (spot + margen) por año, con el capital ocioso incluido.", ""]


def blocks(res: dict) -> dict:
    """Bloque por estrategia; el carry, en su mejor tenencia (la que se recomienda)."""
    best = [h for h in res["carry_horizons"] if h["horizon_h"] == res["best_carry_h"]]
    return {**res["strategies"], **({"funding_carry": best[0]} if best else {})}


def _main_stats(res: dict, s: str) -> dict | None:
    if s == "triangular":
        return None
    if s == "funding_carry":
        hz = [h for h in res["carry_horizons"] if h["horizon_h"] == res["best_carry_h"]]
        if hz:
            return hz[0]["stats"]
    return res["strategies"][s]["stats"]


def _data(hist: ArbHistory, res: dict) -> list[str]:
    rows = [[k, v, day(hist.coverage.get(k, (None, None))[0]),
             day(hist.coverage.get(k, (None, None))[1])] for k, v in sorted(hist.sources.items())
            if not k.startswith("candles:") or "_" not in k]
    qs = [q for h in hist.assets.values() for q in h.quarterlies]
    qrows = [[q.symbol, day(q.delivery_t), num(q.settle, 1), q.settle_source or "sin precio"]
             for q in qs]
    caps: dict[str, int] = {}
    for prof in hist.depth:
        caps[prof.key] = caps.get(prof.key, 0) + 1
    t_caps = sorted({prof.t for prof in hist.depth})
    return ["## Datos y cobertura", "", *table(["Serie", "Fuente", "Desde", "Hasta"], rows), "",
            "Trimestrales (velas 1 h desde el listado; liquidación = precio real):", "",
            *table(["Contrato", "Vencimiento", "Liquidación", "Fuente"], qrows), "",
            f"Profundidad: **{len(t_caps)} capturas reales** de libros (100 niveles, REST) entre "
            f"{day(t_caps[0] if t_caps else None)} y {day(t_caps[-1] if t_caps else None)}; "
            "claves: " + ", ".join(f"`{k}` ×{n}" for k, n in sorted(caps.items())) + ". No hay "
            "libros históricos: el libro de hoy se aplica al pasado adelgazado por volumen "
            "(volumen medio 24 h / el de la captura, recortado a [mín., 1]: nunca más grueso).",
            "", "Faltantes declarados: " + ("; ".join(f"`{k}`: {v}" for k, v in
                                                      sorted(hist.missing.items())) or "ninguno"),
            "", "Faltas por estrategia en las fotografías: " + (
                "; ".join(f"{s}: {m} ×{n}" for s, m, n in res["missing"]) or "ninguna"), "",
            "Oportunidades no simulables: " + ("; ".join(f"{s}: {m} ×{n}" for s, m, n in
                                                       res["skips"]) or "ninguna"), ""]


def _assumptions(cm: CostModel, p: ArbParams, sp: SimParams) -> list[str]:
    return ["## Supuestos (declarados; no son datos)", "",
            f"- Comisiones: {cm.source}. Rol tomador; liquidación del trimestral = tomador.",
            "- Funding previsto en cada decisión = **última tasa realizada** (el `premiumIndex` "
            "histórico no existe); resto de la tenencia = media de las últimas "
            f"{p.funding_realized_n} realizadas (igual que el motor en vivo). Lo realizado usa "
            "las tasas reales en cada liquidación, a la apertura del perpetuo como marca.",
            "- Ejecución: decisión con el cierre de la vela previa; entrada y salida a la "
            "apertura de la vela siguiente ± deslizamiento del perfil. Índice ≈ spot.",
            f"- Margen: futuros a ×{p.perp_leverage:g}; spot + futuro corto con margen aislado y "
            f"rebalanceo al caer al {sp.rebalance_frac:.0%} del objetivo (vende spot y recompra "
            "futuro); futuro/futuro en margen cruzado (Multi-Assets para USDC-M). Liquidación con "
            "el máximo de la vela: se pierde el margen restante (regla de T25).",
            f"- Pata incompleta: probabilidad {sp.p_fail:.0%} por ejecución de dos patas; un "
            "incidente cuesta deshacer la pata ejecutada (ida y vuelta) y queda expuesta "
            f"{sp.latency_ms:g} ms (escalado √t de rendimientos reales de 15 min).",
            "- Sin préstamo spot (sin histórico de tasas): no se evalúan el carry inverso ni la "
            "base en descuento.", ""]


def _strategies(res: dict) -> list[str]:
    L = ["## Resultados por estrategia", "", f"### {NAMES['funding_carry']}", "",
         *table(["Tenencia", *STATS_HEAD[1:]],
                [stats_row(f"{h['horizon_h']:g} h", h["stats"]) for h in res["carry_horizons"]]),
         ""]
    bl = blocks(res)
    for s in STRATS:
        blk = bl[s]
        st, gap = blk["stats"], blk["est_vs_real"]
        if s != "funding_carry":
            label = "activas" if blk.get("stats_all") else "base"
            L += [f"### {NAMES[s]}", "", *table(STATS_HEAD, [stats_row(label, st)])]
            if blk.get("stats_all"):
                L += ["| " + " | ".join(stats_row("ambas variantes (sin desactivar)",
                                                  blk["stats_all"])) + " |"]
            for g, vst in blk.get("variants", {}).items():
                L += [f"| {g} | " + " | ".join(stats_row(g, vst)[1:]) + " |"]
            L.append("")
            for g, gg in blk.get("gap_by_variant", {}).items():
                if gg.get("n"):
                    L += [f"- {g}: estimado {bps(gg['est_mean_bps'])} → realizado "
                          f"{bps(gg['real_mean_bps'])} (n={gg['n']} decisiones seleccionadas)"]
            if blk.get("gap_by_variant"):
                L.append("")
        else:
            L += [f"El motor en vivo usa {res['carry_h_live']:g} h. Desglose y distribución "
                  f"siguientes: mejor tenencia ({res['best_carry_h']:g} h).", ""]
        if st.get("n"):
            L += [f"Desglose (USD, suma): {breakdown(st['costs'])}. Rebalanceos: "
                  f"{st['rebalances']}; liquidaciones: {st['liquidations']}; ocupación del "
                  f"capital: {st['invested_frac']:.0%}.", "",
                  "Distribución por operación (sobre capital): " + ", ".join(
                      f"p{k} {bps(v)}" for k, v in st["pcts_bps"].items()) + "; con incidentes "
                  f"de pata sorteados: p1 {bps(st['mc_pcts_bps'][1])}, p5 "
                  f"{bps(st['mc_pcts_bps'][5])}, peor {bps(st['mc_worst_bps'])}.", "",
                  "Por año de entrada: " + "; ".join(f"{y}: {d['n']} op., "
                                                     f"{num(d['net_usd'], 0)} USD "
                                          f"({pct(d['apr'])} anual)"
                                          for y, d in st["by_year"].items()), ""]
        if gap.get("n"):
            L += [f"Estimado por el motor vs realizado (seleccionadas, n={gap['n']}): "
                  f"{bps(gap['est_mean_bps'])} → {bps(gap['real_mean_bps'])} "
                  f"(desvío {bps(gap['real_minus_est_bps'])}).", ""]
    return L


def _legging(res: dict, sp: SimParams) -> list[str]:
    L = ["## Riesgo de pata incompleta (una pata ejecuta y la otra no)", ""]
    for a, blk in res["legging"].items():
        L += [f"{a}: deshacer la pata spot de 10 000 USD cuesta {bps(blk['undo_bps'])} (ida y "
              f"vuelta); pérdida por incidente según la latencia:", "",
              *table(["Latencia", "Media", "p95", "p99", "Máx.", f"Esperado/ejecución "
                      f"(p={sp.p_fail:.0%})", "Desv. 2.ª pata"],
                     [[f"{r['latency_ms']:g} ms", bps(r["mean_bps"]), bps(r["p95_bps"]),
                       bps(r["p99_bps"]), bps(r["max_bps"]), bps(r["expected_per_event_bps"], 2),
                       bps(r["drift_std_bps"], 2)] for r in blk["rows"]]), ""]
    bl = blocks(res)
    for s in STRATS:
        lm, pf = bl[s]["latency_mc"], bl[s]["p_fail"]
        if lm:
            L += [f"{NAMES[s]} — neto por operación con incidentes sorteados: " + "; ".join(
                f"{r['latency_ms']:g} ms: p5 {bps(r['p5_bps'])}, peor {bps(r['worst_bps'])}"
                for r in lm) + ". Prob. de incidente: " + "; ".join(
                f"{r['p_fail']:.0%} → {bps(r['mean_bps'])}/op" for r in pf) + ".", ""]
    return L


def _sensitivity(res: dict) -> list[str]:
    sens = res.get("sensitivity")
    if not sens:
        return []
    head = ["Caso", *[NAMES[s] for s in STRATS]]
    L = [f"## Sensibilidad (decisión cada {sens['every_h']} h; celda = operaciones · anual "
         "período · neto medio)", ""]
    for title, key, fmt in (("Comisiones (nivel VIP / BNB)", "fees", str),
                            ("Nocional por operación (capacidad)", "notional",
                             lambda n: f"{num(float(n))} USD"),
                            ("Profundidad (libro × escala)", "depth", lambda d: f"×{d:g}"),
                            ("Apalancamiento de las patas de futuros", "leverage",
                             lambda v: f"×{v:g}")):
        L += [f"### {title}", "", *table(head, [brief_row(fmt(k), row, STRATS)
                                               for k, row in sens[key].items()]), ""]
    return L


def _opportunities(res: dict) -> list[str]:
    L = ["## Oportunidades reales y significancia", "",
         "Por umbral de neto estimado por el motor: lo realizado de todas las decisiones que lo "
         "superan (se solapan: IC por bootstrap en bloques del largo de la tenencia) y la "
         "política de una posición a la vez con ese umbral.", ""]
    items = [(s, res["strategies"][s], "") for s in STRATS]
    items.insert(1, ("funding_carry", blocks(res)["funding_carry"],
                     f" (tenencia {res['best_carry_h']:g} h)"))
    for s, blk, tag in items:
        c = blk["counts"]
        if s == "funding_carry" and not tag:
            tag = f" (tenencia del motor en vivo, {res['carry_h_live']:g} h)"
        L += [f"**{NAMES[s]}{tag}**: {c['decisions']} decisiones, {c['valued']} valoradas, "
              f"{c['selected']} seleccionadas por el motor ({c['selected_positive']} con "
              f"realizado > 0); descartes: " + ", ".join(f"{k} {v}" for k, v in
                                                        c["rejected_by_code"].items()) + "."
              + ("" if not c.get("score_pcts") else " Puntuación del selector de las "
                 "seleccionadas (pb/día ajustados por riesgo, la de las alertas T39): " + ", ".join(
                     f"p{k} {v:.2f}".replace(".", ",") for k, v in c["score_pcts"].items())
                 + "."), "",
              *table(["Umbral neto estimado", "n", "Estimado medio", "Realizado medio",
                      "IC95 %", "p ≤ 0", "% > 0", "Política: op.", "Política: anual"],
                     [[("todas" if r["theta"] < -1e8 else bps(r["theta"], 0)), str(r["n"]),
                       bps(r.get("est_mean_bps")), bps(r.get("real_mean_bps")), ci(r.get("ci95")),
                       "—" if r.get("p_le0") is None or r["p_le0"] != r["p_le0"]
                       else f"{r['p_le0']:.3f}".replace(".", ","),
                       pct(r.get("share_pos"), 0).lstrip("+"), str(r.get("policy_n", "—")),
                       pct(r.get("policy_apr"))] for r in blk["sweep"] if r["n"]]), ""]
    return L
