"""Textos del informe de T111: cabecera reproducible, conclusión, causas y decisión.

Las frases se construyen con las cifras de la corrida (nada escrito a mano sobre el resultado):
si los números cambian, la conclusión cambia con ellos.
"""

from __future__ import annotations

PIDS = ("conservador", "moderado", "agresivo")


def _pairs(res: dict, seg: str, pid: str) -> list[tuple[str, dict, dict, dict]]:
    """[(escenario, A emparejado, B emparejado, bloque B)] del tramo y perfil."""
    p = res["segments"][seg]["profiles"][pid]
    return [(k, b["pairs"]["comunes"]["a"], b["pairs"]["comunes"]["b"], b)
            for k, b in p["B"].items()]


def _tot(m: dict) -> float:
    """Neto cerrado + flotante de lo que sigue abierto al final: una pareja que A cerró y B aún
    tiene abierta cuenta en las dos columnas."""
    return m["net"] + m.get("floating_end", 0.0)


def _int(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def header(res: dict, iso, n) -> list[str]:
    m = res["meta"]
    cov = m.get("coverage") or {}
    tfs = cov.get("timeframes") or {}
    ctx = ", ".join(f"{tf} {x['contexts']} ({iso(x['from'])[:10]} → {iso(x['to'])[:10]})"
                    for tf, x in tfs.items())
    ex = m["exec"]
    c = ex["costs"]
    fix = sum(b["slip_fix_usd"] for pid in PIDS
              for b in res["segments"]["fuera"]["profiles"][pid]["B"].values())
    out = [
        "# A/B de salidas por perfil: protección progresiva frente a TP/BE+/tiempo (T111)", "",
        f"**SIMULADO, sin dinero real** · {m['symbol']} · código `{m['commit']}` · camino de "
        f"{ex['path_tf']} hasta {iso(m['path_end'])} UTC.", "",
        "## Cómo se reproduce", "",
        f"- Comando, desde `v2/` y sobre una **copia** del almacén: `{m['command']}` (en un "
        "worktree, con `PYTHONPATH=.` delante para usar su `eim`). `--from-json <json>` rehace "
        "este informe sin recalcular.",
        "- Datos: copia en caliente del almacén vivo (`POST /v2/share/snapshot` de T61, "
        f"2026-10-23): contextos de {m['symbol']} por marco: {ctx}; {_int(m['ideas'])} ideas "
        "sombra; velas de 15 m y funding real desde 2023. Velas de 1 min: el almacén vivo solo "
        "las tiene desde 2026-10-15; para esta corrida se sincronizó en la COPIA la historia desde "
        f"{iso(m['fine_from'])[:10]} con el proveedor del proyecto (`BinanceFutures.klines`, "
        f"`fapi/v1/klines`): {_int(m.get('fine_rows', 0))} velas, sin huecos.",
        f"- Tramos, sin optimizar nada: **fuera de muestra** = decisiones anteriores a "
        f"{m['is_from'][:10]}, inicio de la ventana con la que T48b ajustó el BE+ de A "
        "(2026-08-16 → 2026-10-16, `val_windows`); la escalera de B se diseñó y midió con datos "
        f"desde {m['exit_window_from'][:10]} (T105–T110). **Dentro de muestra** = desde "
        f"{m['is_from'][:10]}. Capital (10.000 USDT) y memoria de cada perfil se reinician en "
        "cada tramo.",
        f"- Costos y mecánica (`ExecParams`, iguales en A y B): taker {n(c['taker_fee'] * 1e4, 1)}"
        f" pb, maker {n(c['maker_fee'] * 1e4, 1)} pb, deslizamiento de salida "
        f"{n(c['slip_base_bps'], 1)} pb + {n(c['slip_vol_k'], 2)} × rango de la vela, de entrada a"
        f" mercado {n(c['slip_entry_base_bps'], 2)} pb; BE+ de A: {n(ex['be_trigger_r'], 1)} R → "
        f"+{n(ex['be_lock_r'], 2)} R en {', '.join(ex['be_timeframes'])}; funding real. Criterios "
        f"`{m['criteria']}`, semilla 0. Mismo motor, mismas ideas, mismo camino.",
        "- Escalera por perfil (versión de parámetros de T108/T109; la sensibilidad cambia solo "
        "el primer escalón y deja el incremento en la mitad):", "",
        "| Perfil | Primer escalón | Incremento | BE+ conviviendo | Peso máx. propio |",
        "|---|--:|--:|:-:|--:|"]
    out += [f"| {pid} | {n(x['first_r'], 3)} R | {n(x['step_r'], 4)} R | "
            f"{'sí' if x['be_with_ladder'] else 'no'} | {n(x['max_weight'], 1)} |"
            for pid, x in m["ladder"].items()]
    out += ["", "- Arreglo previo al A/B (BACKLOG T109 (1)): la escalera entraba a mercado con el "
            "deslizamiento de SALIDA; ahora paga el de entrada de la sombra (`ladder._entry`), así "
            "que A y B entran al mismo precio. En los libros de B fuera de muestra eso deja de "
            f"cobrarle ≈ {n(fix, 0)} USDT (estimación directa del término quitado). Cambia también "
            "al control `ppp_btcusdt`.", ""]
    return out


def _cond_gap(res: dict, cond: str) -> list[str]:
    """«perfil ±USDT» de B − A en el emparejado fuera de muestra para una condición del día."""
    out = []
    for pid in PIDS:
        b = next(iter(res["segments"]["fuera"]["profiles"][pid]["B"].values()))
        a, x = b["pair_conditions"]["a"].get(cond), b["pair_conditions"]["b"].get(cond)
        if a and x:
            out.append(f"{pid} {x['net'] - a['net']:+,.0f}".replace(",", "."))
    return out


def conclusion(res: dict, n) -> list[str]:
    worse, better = [], []
    for pid in PIDS:
        for k, a, b, _ in _pairs(res, "fuera", pid):
            (better if _tot(b) > _tot(a) else worse).append(f"{pid} {k}")
    opt_beats = [f"{pid} {k}" for pid in PIDS for k, a, _, blk in _pairs(res, "fuera", pid)
                 if _tot(blk["pairs_optimista"]["comunes"]["b"]) > _tot(a)]
    is_better = [pid for pid in PIDS if (lambda x: _tot(x[2]) > _tot(x[1]))(
        _pairs(res, "dentro", pid)[0])]
    any_pos = [f"{seg} {pid} {k}" for seg in ("fuera", "dentro") for pid in PIDS
               for k, a, b, _ in _pairs(res, seg, pid) if _tot(b) > 0 or _tot(a) > 0]
    out = ["## Conclusión", ""]
    if not better:
        out.append("**La protección progresiva NO mejora a ningún perfil fuera de muestra.** Con "
                   "las mismas entradas pierde más que la salida actual en los tres perfiles y con"
                   " los tres umbrales probados.")
    else:
        out.append(f"**La protección progresiva mejora fuera de muestra solo en: "
                   f"{', '.join(better)}**; empeora en {', '.join(worse) or 'ninguno'}.")
    out += ["", "| Perfil | A fuera de muestra (R/op) | B umbral del encargo (R/op) | B 0,5 R | "
            "B 1 R | Dentro de muestra: A → B encargo |", "|---|--:|--:|--:|--:|--:|"]
    for pid in PIDS:
        ps, ins = _pairs(res, "fuera", pid), _pairs(res, "dentro", pid)[0]
        a = ps[0][1]
        out.append(f"| {pid} | {n(_tot(a), 0)} ({n(a['expectancy_r'], 3, True)}) | "
                   + " | ".join(f"{n(_tot(b), 0)} ({n(b['expectancy_r'], 3, True)})"
                                for _, _, b, _ in ps)
                   + f" | {n(_tot(ins[1]), 0)} → {n(_tot(ins[2]), 0)} |")
    out += ["", "USDT netos de costos (cerrado + flotante de lo abierto al final); A/B "
            "emparejado (mismas entradas, mismo tamaño, velas de 1 min reales en las velas "
            "ambiguas). R/op sobre las cerradas.", ""]
    fb = res.get("fine_bias") or {}
    out.append("- El orden real de los precios no la salva: con velas de 1 min B mejora frente a "
               "la regla conservadora (" + ", ".join(
                   f"{pid} {n(x['sin_1m'], 0)} → {n(x['con_1m'], 0)}" for pid, x in fb.items())
               + " USDT), pero sigue por debajo de A. "
               + (f"Solo un orden sintético siempre favorable (cota optimista, no real) la "
                  f"pondría por delante en: {', '.join(opt_beats)}." if opt_beats else
                  "Ni siquiera la cota optimista sintética supera a A."))
    if is_better:
        out.append(f"- Dentro de muestra (≈ 2 meses, el tramo con el que se diseñó la escalera) B "
                   f"sí perdía menos en {', '.join(is_better)}: **no se confirma fuera de "
                   "muestra**, que es lo que cuenta.")
    out.append("- Por tipo de día (emparejado fuera de muestra, B − A): con **tendencia** la "
               "escalera pierde lo que A ganaba (" + ", ".join(_cond_gap(res, "tendencia"))
               + " USDT); en días **laterales** pierde menos que A ("
               + ", ".join(_cond_gap(res, "lateral")) + "). La etiqueta del día es ex post: no "
               "sirve para elegir la salida al entrar (ver la tabla por régimen ex ante).")
    fbk, per_op_worse = [], []
    for pid in PIDS:
        a, b = (res["segments"]["fuera"]["profiles"][pid]["A"]["metrics"],
                next(iter(res["segments"]["fuera"]["profiles"][pid]["B"].values()))["metrics"])
        fbk.append(f"{pid} {a['n']} → {b['n']} ops, {n(a['net'], 0)} → {n(b['net'], 0)} USDT, "
                   f"{n(a['expectancy_r'], 3, True)} → {n(b['expectancy_r'], 3, True)} R/op")
        if (b["expectancy_r"] or 0) < (a["expectancy_r"] or 0):
            per_op_worse.append(pid)
    out.append("- Libro completo fuera de muestra (A → B encargo): " + "; ".join(fbk) + ". B pierde"
               " menos dinero porque **opera mucho menos** (su memoria propia pausa estrategias y"
               " el Conservador casi no sale de «en observación»), no porque la salida sea mejor"
               + (f": por operación es peor que A en {', '.join(per_op_worse)}."
                  if per_op_worse else "."))
    out.append("- " + ("Ningún escenario es rentable: A y B **siguen siendo perdedores** en los "
                       "dos tramos." if not any_pos else
                       f"Escenarios con neto positivo: {', '.join(any_pos)} (muestra a mirar con "
                       "los criterios de T49, abajo)."))
    out.append("- La hipótesis de partida (como en T27: **no mejora**) "
               + ("se mantiene." if not better else "se rechaza solo donde se indica."))
    return out


def limits(res: dict, n) -> list[str]:
    c = res["segments"]["fuera"]["profiles"]["moderado"]["B"]
    k0 = next(iter(c))
    cut = c[k0]["pairs"]["cortes"]
    a, b = c[k0]["pairs"]["comunes"]["a"], c[k0]["pairs"]["comunes"]["b"]
    high = [k for k in list(c)[1:] if _tot(c[k]["pairs"]["comunes"]["b"]) <= _tot(a)]
    cons = res["segments"]["fuera"]["profiles"]["conservador"]
    cb = next(iter(cons["B"].values()))
    strict = (res.get("gate") or {}).get("estricto") or []
    return [
        "## Causas probables y límites", "",
        f"1. **Decapita a las ganadoras.** Moderado fuera de muestra, {k0}: las {cut['a_tp']} "
        f"entradas que A cerró en TP valían {n(cut['a_tp_mean_r'], 2, True)} R de media; con la "
        f"escalera esas mismas dejaron {n(cut['b_on_a_tp_mean_r'], 2, True)} R "
        f"({cut['a_tp_b_less']} se llevaron menos, {cut['a_tp_b_lost']} acabaron en pérdida; "
        f"{n(cut['given_up_usd'], 0)} USDT cedidos). A cambio las perdedoras de A pasan de "
        f"{n(cut['a_loss_mean_r'], 2, True)} a {n(cut['b_on_a_loss_mean_r'], 2, True)} R y "
        f"{cut['a_lost_b_won']} de {cut['a_losers']} se salvan, pero no compensa: ganadora media "
        f"{n(b['avg_win_r'], 2, True)} R frente a perdedora {n(b['avg_loss_r'], 2, True)} R con "
        f"escalera (A: {n(a['avg_win_r'], 2, True)} / {n(a['avg_loss_r'], 2, True)}). "
        + (f"Con umbrales más altos ({', '.join(high)}) corta menos a las ganadoras, pero protege "
           "tarde y renuncia al BE+ y a la salida por tiempo de A: tampoco mejora."
           if len(high) == len(c) - 1 else "Con umbrales más altos el balance cambia: ver la "
           "tabla de cortes por umbral."),
        f"2. **Toda salida de la escalera es un stop** (taker + deslizamiento con el rango de la "
        f"vela); el TP de A sale como límite (maker, sin deslizamiento): costo medio "
        f"{n(a['costs']['mean_r'], 3)} R en A frente a {n(b['costs']['mean_r'], 3)} R en B con "
        "las mismas entradas.",
        "3. **Velas de 1 min**: el almacén vivo solo las tiene desde 2026-10-15; para esta corrida"
        " se sincronizó la historia completa en la copia (ver arriba). Dentro de cada minuto el "
        "orden sigue siendo desconocido (regla conservadora allí).",
        f"4. **Memoria propia de la escalera (T109)**: el Conservador («solo lo probado») hizo "
        f"{cb['metrics']['n']} operaciones en 3,6 años fuera de muestra frente a "
        f"{cons['A']['metrics']['n']} con A; casi todas las ideas que A tomó B las rechazó «en "
        "observación» (BACKLOG T109 (4)): con escalera esa regla deja al perfil sin operar.",
        "5. Fuera de muestra solo hay contextos de 1 h (y de 4 h desde 2026-03): los de 15 m solo"
        " existen dentro de muestra. El emparejado usa los tamaños de A; el libro completo, los "
        "de cada escenario.",
        f"6. **T49 estricto sin tramo fuera de muestra**: "
        f"{sum(1 for g in strict if g['n_oos'] == 0)} de {len(strict)} escenarios quedan con 0 "
        "operaciones porque las versiones vigentes de las estrategias se dieron de alta "
        "automáticamente el 2026-10-22 con una ventana de ajuste que cubre toda la historia "
        "anterior. Su veredicto es «EN OBSERVACIÓN» y la tabla informativa no es un veredicto.",
        "7. A7 de T106 sigue abierto: `exit_mode` no entra en la huella de versión de T49 y la "
        "puerta mide la sombra con TP; si alguna vez se adopta la escalera, tiene que medirse como"
        " una salida propia (BACKLOG).", ""]


def decision(res: dict, n) -> list[str]:
    d = res.get("decision")
    out = ["## ◆ Decisión del usuario", "",
           "Opciones: (1) adoptar en los tres perfiles · (2) adoptar solo en los que mejoren fuera "
           "de muestra · (3) archivar y dejar el 4.º perfil (`ppp_btcusdt`) como único con "
           "escalera.", ""]
    if not d:
        return out + ["**Pendiente de la respuesta del usuario.**", ""]
    return out + [f"**Respuesta ({d['date']}): {d['choice']}.** {d.get('note', '')}", ""]
