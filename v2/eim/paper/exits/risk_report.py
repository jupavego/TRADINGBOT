"""Informe de T136: riesgo con costos, tope, frenos, Kelly y ES. Puro: del dict al markdown."""

from __future__ import annotations

NA = "—"


def _n(x, k: int = 4, sign: bool = True) -> str:
    if x is None or isinstance(x, bool):
        return NA if x is None else ("sí" if x else "no")
    if not isinstance(x, (int, float)):
        return str(x)
    return f"{x:+.{k}f}" if sign else f"{x:.{k}f}"


def _pct(x, k: int = 2) -> str:
    return NA if x is None else f"{x:.{k}f} %"


def _frac(x, k: int = 1) -> str:
    """Fracción (0,761) como porcentaje (76,1 %)."""
    return NA if x is None else f"{100 * x:.{k}f} %"


def _head(res: dict) -> list[str]:
    m, w = res["meta"], res["window"]
    return [
        "# T136 — Riesgo por operación con costos y control de drawdown gradual",
        "",
        f"Copia `{m['data']}` · {m['symbol']} · salida `{m['policy']}` (la vigente) · "
        f"pre-registro `{m['prereg']}` (`{m['prereg_sha256'][:12]}…`) · commit `{m['commit']}` · "
        f"{m['built']} · {m['seconds']} s",
        "",
        f"Ventana {w['from']} → {w['to']} · {w['folds']} pliegues · embargo "
        f"{w['embargo_hours']:.1f} h · {w['n_closed']} operaciones cerradas, "
        f"**{w['n_tested']} fuera de muestra** (las únicas que se usan aquí).",
        "",
        "Nada de esto cambia a ningún perfil: todos los interruptores nuevos "
        "(`risk_includes_costs`, `dd_steps`, `cvar_limit_r`, Kelly) salen **apagados**. "
        "Encenderlos es decisión ◆ del usuario, y esta medición es para tomarla.",
        "",
    ]


def _costs(res: dict) -> list[str]:
    c, caps = res["costs"], res["cost_caps"]
    out = ["## 1. El costo que el riesgo no incluye", "",
           f"Costo **ex ante** medio (el que el perfil estima al decidir, y con el que veta): "
           f"**{_n(c['cost_r_ex_ante']['mean'], 4, False)} R** "
           f"(mediana {_n(c['cost_r_ex_ante']['median'], 4, False)}, "
           f"p90 {_n(c['cost_r_ex_ante']['p90'], 4, False)}). Costo **realizado** medio "
           f"{_n(c['cost_r_real']['mean'], 4, False)} R.", "",
           f"Dimensionando como hoy, al saltar el SL inicial no se pierde el riesgo declarado "
           f"sino **×{_n(c['risk_overrun'], 4, False)}**: un perfil que dice arriesgar 0,5 % "
           f"arriesga {0.5 * c['risk_overrun']:.3f} %. Incluir el costo en el presupuesto "
           f"multiplica la cantidad por **{_n(c['qty_ratio_with_costs'], 4, False)}** y deja la "
           f"pérdida al stop exactamente en lo declarado.", "",
           "| Marco | n | Costo ex ante medio | Costo realizado medio | Se arriesga de más |",
           "|---|--:|--:|--:|--:|"]
    for tf, g in c["by_timeframe"].items():
        out.append(f"| {tf} | {g['n']} | {_n(g['cost_r_ex_ante_mean'], 4, False)} R | "
                   f"{_n(g['cost_r_real_mean'], 4, False)} R | "
                   f"{_pct(g['overrun_pct'], 1)} |")
    if "15m" not in c["by_timeframe"]:
        out += ["", "**Esta cifra es una cota por abajo de lo que pasa en vivo.** El banco de "
                    "T131 se pre-registró con marcos de decisión 1 h y 4 h, así que aquí no hay "
                    "ni una operación de **15 m**, que es el marco donde el stop está más cerca "
                    "y el costo pesa más (T48b lo midió en 0,48 R por operación con 4 034 ops). "
                    "Los perfiles sí operan 15 m en vivo, de modo que el exceso real sobre el "
                    "riesgo declarado es mayor que el medido aquí. Medirlo exige un banco con "
                    "15 m, que es una versión nueva del pre-registro."]
    out += ["", "## 2. El tope de costo en R (rejilla de §4.5)", "",
            "Con el costo **ex ante**, que es el que decide el veto. «Entra» es la fracción de "
            "operaciones fuera de muestra que el tope dejaría pasar.", "",
            "| Tope | Entra | n | E[R] | Acierto | PF | CVaR 95 % |",
            "|--:|--:|--:|--:|--:|--:|--:|"]
    for g in caps:
        out.append(f"| {g['cap_r']:.2f} R | {_frac(g['share'])} | {g['n']} | "
                   f"{_n(g['expectancy_r'])} | {_frac(g['win_rate'])} | "
                   f"{_n(g['pf'], 3, False)} | {_n(g['cvar95_r'])} |")
    hoy = {p: v["max_cost_r"] for p, v in res["profiles_today"].items()}
    tops = " · ".join(f"`{k}` {v:.2f} R" for k, v in hoy.items())
    out += ["", f"Topes de hoy por perfil: {tops}.", ""]
    return out


def _brakes(res: dict) -> list[str]:
    s3 = res["prereg_s3"]
    out = ["## 3. Frenos: todo o nada frente a gradual (rejilla pre-registrada de S3)", "",
           f"Valores pre-registrados: `dd_brake` {s3['dd_brake']}, "
           f"`cvar_limit_r` {s3['cvar_limit_r']}, `vol_target` {s3['vol_target']}. El freno "
           "gradual no tiene rejilla propia, así que se construye desde la que hay: último tramo "
           "en el `dd_brake` pre-registrado y tramo intermedio en su mitad con el riesgo a la "
           "mitad. Se simula el capital con los mismos `caps` que corren en el libro.", ""]
    for pid, rows in res["brakes"].items():
        pct = res["profiles_today"][pid]["risk_pct"]
        out += [f"### `{pid}` (riesgo {pct:.2%} por operación)", "",
                "| Caso | Tomadas | Frenadas | Recortadas | Capital final | Retorno | "
                "DD máx. | CVaR 95 % | ¿ruina? |", "|---|--:|--:|--:|--:|--:|--:|--:|---|"]
        for g in rows:
            out.append(f"| {g['caso']} | {g['n_taken']} | {g['halted']} | {g['cut']} | "
                       f"{g['equity_final']:,.0f} | {_pct(g['return_pct'], 1)} | "
                       f"{_pct(g['max_dd_pct'], 1)} | {_n(g['cvar95_r'])} | "
                       f"{'**sí**' if g['ruined'] else 'no'} |")
        out.append("")
    out += ["### Pliegue a pliegue (tres meses cada uno, capital nuevo)", "",
            "De corrido, 3,5 años de un sistema con E[R] < 0 arruinan la cuenta en **cualquier** "
            "configuración, así que la tabla de arriba no distingue entre frenos: lo único que "
            "evita la ruina es dejar de operar. Por pliegue sí se ve qué hace cada uno.", ""]
    for pid, rows in res.get("brakes_by_fold", {}).items():
        out += [f"#### `{pid}`", "",
                "| Caso | Pliegues | Retorno mediano | Peor pliegue | DD mediano | "
                "Tomadas (mediana) | Pliegues arruinados |",
                "|---|--:|--:|--:|--:|--:|--:|"]
        for g in rows:
            out.append(f"| {g['caso']} | {g['folds']} | {_pct(g['return_median_pct'], 1)} | "
                       f"{_pct(g['return_worst_pct'], 1)} | {_pct(g['dd_median_pct'], 1)} | "
                       f"{g['taken_median']:.0f} | {g['ruined_folds']} |")
        out.append("")
    lim = res["prereg_s3"]["cvar_limit_r"]
    base_cvar = res["metrics"].get("cvar95_r")
    pide = ", ".join(f"{-x:.2f}" for x in lim)
    out += [f"**Los límites de CVaR pre-registrados son inalcanzables.** El CVaR 95 % real de "
            f"la salida vigente es {_n(base_cvar)} R y la rejilla pide {pide} R, "
            f"así que el límite está activo "
            f"permanentemente y recorta casi todas las entradas: no es un control de cola, es un "
            f"recorte fijo del tamaño. Se informa tal como se pre-registró; cambiarlo exige una "
            f"**versión nueva del pre-registro** (E12), no un ajuste aquí.", ""]
    return out


def _kelly(res: dict) -> list[str]:
    k = res["kelly"]
    size = max(k["risk_pct"].values()) if k["risk_pct"] else 0.0
    out = ["## 4. Kelly fraccionado sobre el límite inferior del IC (E10)", "",
           f"Evidencia fuera de muestra: n = {k['n']}, E[R] = {_n(k['mean_r'])} R, error "
           f"estándar agrupado por día {_n(k['se_r'], 4, False)}, E[R²] = "
           f"{_n(k['m2_r'], 4, False)}. Límite inferior con z = {k['z']}: "
           f"**{_n(k['lower_r'])} R**.", "",
           f"Fracción de Kelly ({k['frac']:.0%} de Kelly): **{_n(k['fraction'], 4, False)}** → "
           f"riesgo por operación **{size:.4%}** para todos los perfiles.", ""]
    if size <= 0:
        out += ["Es el resultado correcto y es exactamente lo que la fase 22 ha demostrado: "
                "**sin ventaja, no hay tamaño.** Por eso se entrega apagado: encenderlo hoy "
                "dejaría a los perfiles sin abrir una sola operación y pararía la corrida de "
                "T31 y el A/B de T130.", ""]
    return out


def _es(res: dict) -> list[str]:
    out = ["## 5. Comprobación del ES por pliegue (E12, Acerbi y Székely)", "",
           "Se estima VaR y ES 95 % en el tramo de **ajuste** y se contrasta con la cola del "
           "tramo de **prueba**. Z2 negativo = la cola real es peor que la prevista. El nulo es "
           "un remuestreo por bloques de día del propio tramo de ajuste, no la distribución "
           "predictiva del artículo: es menos exigente y se dice.", "",
           "| Pliegue | Prueba desde | n ajuste | n prueba | ES ajuste | ES prueba | Z2 | p | "
           "Veredicto |", "|--:|---|--:|--:|--:|--:|--:|--:|---|"]
    for g in res["es"]:
        out.append(f"| {g['fold']} | {g['test_from'][:10]} | {g['n_fit']} | {g['n_test']} | "
                   f"{_n(g.get('es_fit_r'))} | {_n(g.get('es_test_r'))} | "
                   f"{_n(g.get('z2'), 3)} | {_n(g.get('p'), 4, False)} | {g['verdict']} |")
    short = [g for g in res["es"] if g.get("es_underestimated")]
    out += ["", f"Pliegues en los que el ES se queda corto: **{len(short)} de "
                f"{len(res['es'])}**.", ""]
    return out


def _vol(res: dict) -> list[str]:
    v = res["vol_target"]
    out = ["## 6. Tamaño por volatilidad objetivo (entregable 3, opcional)", "",
           f"Con la σ versionada de T132 (`{res['meta']['sigma']}`), cobertura "
           f"{_frac(res['sigma_coverage']['coverage'].get('sigma_abs', 0))}. Operaciones con "
           f"σ: {v['n']} · σ relativa mediana {_n(v['sigma_median'], 5, False)}.", "",
           "| Caso | Peso mediano | E[R] | Desv. típica de R | CVaR 95 % |",
           "|---|--:|--:|--:|--:|",
           f"| sin escalar | 1,0 | {_n(v['base']['expectancy_r'])} | "
           f"{_n(v['base']['sd_r'], 4, False)} | {_n(v['base']['cvar95_r'])} |"]
    for g in v["targets"]:
        out.append(f"| objetivo {g['label']} (saturado {_frac(g['saturated'])}) | "
                   f"{_n(g['weight_median'], 2, False)} | "
                   f"{_n(g['expectancy_r'])} | {_n(g['sd_r'], 4, False)} | "
                   f"{_n(g['cvar95_r'])} |")
    out.append("")
    sat = [g for g in v["targets"] if g["label"] != "mediana" and g["saturated"] > 0.9]
    if sat:
        out += [f"**Los objetivos pre-registrados no están en las unidades de esta σ.** "
                f"{', '.join(g['label'] for g in sat)} dejan el multiplicador en el tope en más "
                f"del 90 % de las operaciones (σ relativa por vela, mediana "
                f"{_n(v['sigma_median'], 5, False)}), así que como están escritos no miden nada. "
                f"La fila `mediana` es el único objetivo sin parámetro libre: la σ mediana de la "
                f"propia muestra. Corregir las unidades exige una **versión nueva del "
                f"pre-registro**, no un ajuste aquí (E12).", ""]
    return out


def render(res: dict) -> str:
    """El informe completo en markdown."""
    parts = (_head(res) + _costs(res) + _brakes(res) + _kelly(res) + _es(res) + _vol(res))
    parts += ["## Lo que esto no es", "",
              "- No elige ninguna salida: eso lo cerró T134 (87 de 87 rechazadas).",
              "- No habilita dinero real ni toca la corrida en vivo.",
              "- El tamaño por volatilidad objetivo es una **medición**: aplicarlo exige la "
              "misma σ en el stop y en el tamaño (E11), y el stop sigue siendo el de la "
              "escalera.", ""]
    return "\n".join(parts)
