"""Informe Markdown del A/B de T111 (lo escribe `ppp_profiles_ab.py`; los textos viven en
`ppp_ab_text.py`). Solo da formato: todas las cifras salen del JSON de la corrida."""

from __future__ import annotations

from datetime import UTC, datetime

from ppp_ab_text import conclusion, decision, header, limits

PIDS = ("conservador", "moderado", "agresivo")
SEG = {"fuera": "Fuera de muestra", "dentro": "Dentro de muestra"}
CONDS = ("tendencia", "intermedio", "lateral", "vol_alta", "vol_baja", "brusco", "sin_brusco")
COND_NAME = {"tendencia": "Tendencia", "intermedio": "Intermedio", "lateral": "Lateral",
             "vol_alta": "Volatilidad alta", "vol_baja": "Volatilidad baja",
             "brusco": "Con movimiento brusco", "sin_brusco": "Sin movimiento brusco"}


def iso(t) -> str:
    return "—" if t is None else datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def n(x, d: int = 2, sign: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, d: int = 0) -> str:
    return "—" if x is None else n(x * 100, d) + " %"


def exits(m: dict) -> str:
    e = m["exits"]
    parts = [("SL ini", e["stop_inicial"]), ("SL din", e["stop_dinamico"]), ("TP", e["tp"]),
             ("BE", e["be"]), ("tiempo", e["tiempo"]), ("liq.", e["liquidacion"]),
             ("salv.", e["salvaguarda"]), ("otros", e["otros"])]
    return " · ".join(f"{k} {v}" for k, v in parts if v)


def summary_table(seg: dict, mode: str) -> list[str]:
    acct = mode == "libro"
    head = ("| Perfil | Escenario | Ops | Acierto | Ganado | Perdido | Neto USDT | PF | "
            "Esperanza R | Esperanza USDT | " + ("Capital final | Rentab. | DD equity | "
                                                if acct else "DD (R) | ")
            + "Costos USDT | Costo R | Activó prot. | Cierres |")
    cols = head.count("|") - 1
    out = [head, "|" + "|".join(["---"] * 2 + ["--:"] * (cols - 3) + ["---"]) + "|"]
    for pid in PIDS:
        p = seg["profiles"][pid]
        rows = []
        if acct:
            rows.append(("A (TP/BE+/tiempo)", p["A"]["metrics"]))
            rows += [(k, b["metrics"]) for k, b in p["B"].items()]
        else:
            first = next(iter(p["B"].values()))["pairs"]["comunes"]["a"]
            rows.append(("A (TP/BE+/tiempo)", first))
            rows += [(k, b["pairs"]["comunes"]["b"]) for k, b in p["B"].items()]
        for lab, m in rows:
            pr = m["protection"]
            mid = (f"{n(m['capital']['final_equity'], 0)} | {pct(m['capital']['return_pct'], 1)} | "
                   f"{pct(m['max_dd_pct'], 1)}" if acct else n(m["max_dd_r"], 1))
            out.append(
                f"| {pid} | {lab} | {m['n']} | {pct(m['win_rate'])} | {n(m['net_won'], 0)} | "
                f"{n(m['net_lost'], 0)} | **{n(m['net'], 0)}** | {n(m['pf'])} | "
                f"{n(m['expectancy_r'], 3, True)} | {n(m['expectancy_usd'], 2, True)} | {mid} | "
                f"{n(m['costs']['total'], 0)} | {n(m['costs']['mean_r'], 3)} | "
                f"{pr['activated'] if pr else '—'} | {exits(m)} |")
    return out


def pair_note(seg: dict) -> str:
    p = seg["profiles"]
    bits = []
    for pid in PIDS:
        for k, b in p[pid]["B"].items():
            pm = b["pairs"]
            if pm["vetadas_en_b"]["a"]["n"] or pm["no_negociables_en_b"]:
                bits.append(f"{pid} {k}: {pm['vetadas_en_b']['a']['n']} vetadas por la viabilidad"
                            f" de B (A {n(pm['vetadas_en_b']['a']['net'], 0)} USDT, B "
                            f"{n(pm['vetadas_en_b']['b']['net'], 0)}), "
                            f"{pm['no_negociables_en_b']} no negociables")
    fills = all(b["pairs"]["mismo_llenado"] == b["pairs"].get("negociables", b["pairs"]["n"])
                for x in p.values() for b in x["B"].values())
    return (f"Mismo precio de entrada en A y B: {'todas' if fills else 'NO todas'} las parejas. "
            + ("Entradas que B no habría abierto (contadas aparte, fuera de la tabla): "
               + "; ".join(bits) + "." if bits else
               "Ninguna entrada de A quedaría fuera por el filtro de viabilidad de B."))


def protection_table(seg: dict, mode: str) -> list[str]:
    out = ["| Perfil | Escenario | Activó | Escalones alcanzados (escalón: ops) | Flotante máx. "
           "medio (neto reg.) | Avance máx. medio (precio) | Escalón máx. | Devuelto medio vs "
           "flotante máx. | Realizado − protegido medio | Abiertas fin | Incid. | Inconsist. | "
           "Errores de ejecución |", "|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for pid in PIDS:
        for k, b in seg["profiles"][pid]["B"].items():
            m = b["metrics"] if mode == "libro" else b["pairs"]["comunes"]["b"]
            pr = m["protection"] or {}
            lv = pr.get("levels") or {}
            top = sorted(lv.items(), key=lambda kv: int(kv[0]))
            lvs = ", ".join(f"{a}: {c}" for a, c in top[:8]) + (" …" if len(top) > 8 else "")
            mf, gp = pr.get("max_float_usd") or {}, pr.get("gap_float_vs_final_usd") or {}
            rp = pr.get("realized_vs_protected_usd") or {}
            v = m["violations"]
            out.append(
                f"| {pid} | {k} | {pr.get('activated', 0)} ({pct(pr.get('activation_rate'))}) | "
                f"{lvs or '—'} | {n(mf.get('mean'))} | {n((m['mfe_usd'] or {}).get('mean'))} | "
                f"{pr.get('max_level', 0)} ({n(pr.get('max_level_r'))} R) | {n(gp.get('mean'))} | "
                f"{n(rp.get('mean'), 2, True)} | {m['open_end']} | {m['incidents']} | "
                f"{m['inconsistent']} | {v['executed'] + v['rejected']} |")
    return out


def cuts_table(seg: dict) -> list[str]:
    out = ["| Perfil | Umbral | A cerró en TP (n, R medio) | B en esas mismas: R medio | "
           "B se llevó menos / quedó en pérdida | USDT cedidos | Ganadoras de A: R medio A → B | "
           "Perdedoras de A: R medio A → B | Perdedoras de A que B salvó | Duración media A → B |",
           "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for pid in PIDS:
        for k, b in seg["profiles"][pid]["B"].items():
            c = b["pairs"]["cortes"]
            out.append(
                f"| {pid} | {k} | {c['a_tp']} ({n(c['a_tp_mean_r'], 2, True)}) | "
                f"{n(c['b_on_a_tp_mean_r'], 2, True)} | {c['a_tp_b_less']} / {c['a_tp_b_lost']} | "
                f"{n(c['given_up_usd'], 0)} | {n(c['a_win_mean_r'], 2, True)} → "
                f"{n(c['b_on_a_win_mean_r'], 2, True)} | {n(c['a_loss_mean_r'], 2, True)} → "
                f"{n(c['b_on_a_loss_mean_r'], 2, True)} | {c['a_lost_b_won']} de {c['a_losers']} | "
                f"{n(c['a_hours_mean'], 1)} h → {n(c['b_hours_mean'], 1)} h |")
    return out


def tot(m: dict) -> float:
    """Neto cerrado + flotante de lo abierto al final."""
    return m["net"] + m.get("floating_end", 0.0)


def optimistic_table(seg: dict) -> list[str]:
    out = ["| Perfil | Umbral | A neto (R/op) | B con 1 min reales (R/op) | B cota optimista "
           "sintética (R/op) | ¿La cota supera a A? |", "|---|---|--:|--:|--:|---|"]
    for pid in PIDS:
        for k, b in seg["profiles"][pid]["B"].items():
            a, c = b["pairs"]["comunes"]["a"], b["pairs"]["comunes"]["b"]
            o = b["pairs_optimista"]["comunes"]["b"]
            out.append(f"| {pid} | {k} | {n(a['net'], 0)} ({n(a['expectancy_r'], 3, True)}) | "
                       f"{n(c['net'], 0)} ({n(c['expectancy_r'], 3, True)}) | {n(o['net'], 0)} "
                       f"({n(o['expectancy_r'], 3, True)}) | "
                       f"{'sí' if tot(o) > tot(a) else 'no'} |")
    return out


def cond_table(seg: dict, key: str) -> list[str]:
    out = [f"| Condición ({key}) | " + " | ".join(
        f"{pid}: n · A R/op · B R/op · B−A USDT" for pid in PIDS) + " |",
        "|---|" + "--:|" * len(PIDS)]
    ante = key.startswith("régimen")
    first = next(iter(seg["profiles"][PIDS[0]]["B"].values()))
    conds = (sorted({k for pid in PIDS for k in next(iter(
        seg["profiles"][pid]["B"].values()))["pair_regimes"]["a"]}) if ante else CONDS)
    for c in conds:
        cells = []
        for pid in PIDS:
            b = next(iter(seg["profiles"][pid]["B"].values()))
            if ante:
                a, x = b["pair_regimes"]["a"].get(c), b["pair_regimes"]["b"].get(c)
            elif key == "emparejado":
                a, x = b["pair_conditions"]["a"].get(c), b["pair_conditions"]["b"].get(c)
            else:
                a, x = seg["profiles"][pid]["A"]["conditions"].get(c), b["conditions"].get(c)
            na, nx = (a or {}).get("n", 0), (x or {}).get("n", 0)
            cnt = str(na or nx) if key != "libro completo" else f"{na}/{nx}"
            diff = (x or {}).get("net", 0.0) - (a or {}).get("net", 0.0)
            cells.append("—" if not a and not x else
                         f"{cnt} · {n((a or {}).get('mean_r'), 3, True)} · "
                         f"{n((x or {}).get('mean_r'), 3, True)} · {n(diff, 0, True)}")
        out.append(f"| {COND_NAME.get(c, c)} | " + " | ".join(cells) + " |")
    return out if first else []


def entries_table(seg: dict) -> list[str]:
    out = ["| Perfil | Escenario | Entradas A | Entradas B | Comunes | Solo A | Solo B | Por qué B "
           "no tomó las de A | Entradas por mínimo de abiertas A / B |",
           "|---|---|--:|--:|--:|--:|--:|---|--:|"]
    for pid in PIDS:
        for k, b in seg["profiles"][pid]["B"].items():
            e = b["entries"]
            why = ", ".join(f"{a} {c}" for a, c in e["solo_a_por_motivo"].items()) or "—"
            mo = e["entradas_minimo_abiertas"]
            out.append(f"| {pid} | {k} | {e['a']} | {e['b']} | {e['comunes']} | {e['solo_a']} | "
                       f"{e['solo_b']} | {why} | {mo['a']} / {mo['b']} |")
    return out


def gate_table(rows: list[dict]) -> list[str]:
    out = ["| Escenario | Veredicto | Ops fuera de muestra | R medio | IC95 % | p bruto → Holm | "
           "V1 | V2 | V3 | V4 | V5 | V6 | Motivo |",
           "|---|---|--:|--:|--:|--:|" + ":-:|" * 6 + "---|"]
    mark = {True: "✔", False: "✘", None: "…"}
    for g in rows:
        ck = {c["id"]: c for c in g["checks"]}
        ci = ck["V2"]["value"]["ci"]
        out.append(f"| {g['id'].replace('|', ' · ')} | **{g['verdict']}** | {g['n_oos']} | "
                   f"{n(g['mean_r'], 3, True)} | [{n(ci[0], 3, True)}, {n(ci[1], 3, True)}] | "
                   f"{n(g['p_raw'], 4)} → {n(g['p_holm'], 4)} | "
                   + " | ".join(mark[ck[f"V{i}"]["ok"]] for i in range(1, 7))
                   + f" | {g['reason']} |")
    return out


def render(res: dict) -> str:
    segs, gate = res["segments"], res.get("gate") or {}
    md = header(res, iso, n) + conclusion(res, n) + [""]
    for key in ("fuera", "dentro"):
        s = segs[key]
        md += [f"## {SEG[key]}: {iso(s['from'])} → {iso(s['to'])} UTC", "",
               f"{s['ideas']} ideas sombra (por marco: "
               + ", ".join(f"{tf} {c}" for tf, c in s["timeframes"].items())
               + "); capital y memoria de cada perfil reiniciados al empezar el tramo.", "",
               "### A/B emparejado: las mismas entradas, solo cambia la salida", "",
               "Entradas que A abrió de verdad, con su llenado y su tamaño (redondeado al paso de "
               "BTCUSDT en las dos columnas). Sin cuenta detrás: el drawdown va en R.", "",
               *summary_table(s, "pares"), "", pair_note(s), "",
               "### Libro completo de cada perfil (lo que haría el perfil adoptado)", "",
               "Cada escenario con su propio libro: sus entradas cambian porque los cupos se "
               "liberan antes y porque con escalera el perfil aprende de SUS cierres (T109).", "",
               *summary_table(s, "libro"), "",
               "### Protección: activación, escalones y lo devuelto (libro completo)", "",
               *protection_table(s, "libro"), "",
               "### ¿Corta la escalera a las ganadoras? (emparejado)", "", *cuts_table(s), "",
               "### Condiciones de mercado (umbral del encargo)", "",
               "Etiqueta del día UTC de la decisión, medida con sus velas de 15 m (ex post, "
               "cuantiles fijos de todos los días; ver `ab_conditions.py`), y régimen que el agente"
               " asignó al decidir (ex ante, el único que se conoce antes de entrar).", "",
               *cond_table(s, "emparejado"), "", *cond_table(s, "régimen ex ante, emparejado"),
               "", *cond_table(s, "libro completo"), "",
               "### Entradas: por qué cambian entre A y B (libro completo)", "",
               *entries_table(s), ""]
        if key == "fuera":
            md += ["### Sensibilidad al orden de los precios dentro de la vela", "",
                   "B con velas de 1 min reales (lo de arriba) frente a una cota optimista "
                   "SINTÉTICA: dentro de cada vela de 15 m, siempre primero el extremo a favor y "
                   "luego el contrario. No es un dato real: dice cuánto depende el resultado de "
                   "ese orden.", "",
                   *optimistic_table(s), ""]
    if gate:
        md += ["## Criterios de T49 (validation_v1), tal cual", "",
               "**Estricto** (ventanas de ajuste registradas de cada versión de estrategia + "
               "ventana de las salidas): ", "", *gate_table(gate["estricto"]), "",
               "Excluidas del estricto por escenario: " + "; ".join(
                   f"{k.replace('|', ' · ')}: {v['ventana_estrategia_o_salida']} en ventana, "
                   f"{v['sin_version_registrada']} sin versión" for k, v in
                   gate["excluidas_estricto"].items()) + ".", "",
               "**Informativo, NO es veredicto de T49** (mismos criterios sobre el tramo fuera "
               "de la ventana de las salidas; las entradas sí cayeron en ventanas de ajuste de "
               f"sus estrategias). Holm sobre {gate['intentos_registrados']} intentos "
               "registrados + estos 12.", "", *gate_table(gate["informativo"]), ""]
    md += limits(res, n) + decision(res, n)
    return "\n".join(md) + "\n"
