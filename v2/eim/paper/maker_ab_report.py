"""T143 — informe de la medición maker frente a taker. Solo da formato: no calcula veredictos."""

from __future__ import annotations

import csv
from pathlib import Path


def _s(x: float | None, d: int = 4) -> str:
    """Con signo, para diferencias y para R que puede ser negativo."""
    return "—" if x is None else f"{x:+.{d}f}"


def _f(x: float | None, d: int = 4) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def _head(r: dict) -> list[str]:
    return [
        "# T143 — La entrada maker frente a la taker, emparejada (entregable 1)",
        "",
        f"Modo: **SIMULADO** · {r['symbol']} · banco `{r['banco']}` · marcos "
        f"{', '.join(r['marcos'])} · camino de precios {r['path_tf']} · pre-registro "
        f"`{r['prereg']}` (commit `{r['prereg_commit']}`, anterior a todo cálculo) · generado "
        f"{r['generado']} en {r['segundos']:.0f} s.",
        "",
        "**Nada de este informe cambia un perfil ni habilita dinero real.** No pasa por la puerta "
        "de T49, no reclama ventaja y no reabre T139: mide un costo de ejecución con el criterio "
        "escrito de antemano.",
        "",
        "> **Dos decisiones de contabilidad posteriores al pre-registro, las dos en contra del "
        "brazo maker.** (1) **Denominador común:** el motor divide por el riesgo *realizado* "
        "(`|llenado − SL|`), así que una límite a mejor precio infla su R por aritmética; "
        "todas las cifras de aquí dividen por el riesgo **planeado** (`|entry − SL|`), idéntico en "
        "los dos brazos. (2) **Estrés de cola (§5):** el motor llena si la vela *toca* el nivel, "
        "que es la hipótesis optimista; el estrés exige que el precio **pase** del nivel. Se "
        "añaden porque sin ellas la medición se engaña sola, y las dos solo pueden hacer que maker "
        "salga peor.",
        "",
    ]


def render(r: dict) -> str:
    v, dec = r["veredicto"], r["grid"][f"{r['decide_bars']:g}"]
    tk, mk = dec["taker"], dec["maker"]
    d = dec["delta"]
    out = _head(r)
    out += [
        "## 1. Veredicto",
        "",
        f"**{'SE ADOPTA' if v['adopta'] else 'NO SE ADOPTA'}** la entrada maker: {v['motivo']}.",
        "",
        "| Criterio del pre-registro §4 | Umbral | Medido | ¿Pasa? |",
        "|---|---|--:|---|",
        f"| 1. El costo baja de verdad | ≥ 0,0400 R | {_f(v['costo_baja_r'])} R | "
        f"{'✓' if v['c1_costo'] else '✗'} |",
        f"| 2. El neto por intento no empeora | IC95 % inferior ≥ 0 | {_s(d['lo'])} R | "
        f"{'✓' if v['c2_neto'] else '✗'} |",
        f"| 3. El signo aguanta plazos y años | sin cambio de signo | "
        f"{'estable' if v['c3_estable'] else 'cambia'} | {'✓' if v['c3_estable'] else '✗'} |",
        "",
        _stress_line(r),
        "",
        "## 2. Las cifras que deciden (lectura A: por intento)",
        "",
        f"Las mismas **{tk['intentos']}** decisiones en los dos brazos, con `fill_h` = "
        f"{r['decide_bars']:g} vela y {dec['descartadas']} parejas descartadas por quedar sin "
        "resolver al final del camino. Una orden límite que no se llena cuenta **R = 0**: no es "
        "una operación que sale en tablas, es una decisión que no se ejecutó.",
        "",
        "| | taker (hoy) | maker |",
        "|---|--:|--:|",
        f"| Intentos | {tk['intentos']} | {mk['intentos']} |",
        f"| Operaciones que existieron | {tk['llenadas']} ({tk['llenado_pct']:.1f} %) | "
        f"{mk['llenadas']} ({mk['llenado_pct']:.1f} %) |",
        f"| No llenadas | — | {mk['no_llenada']} |",
        f"| Objetivo alcanzado sin llenar | — | {mk['objetivo_sin_llenar']} |",
        f"| **E[R] neto por intento** | **{_s(tk['neto_r'])}** | **{_s(mk['neto_r'])}** |",
        f"| E[R] bruto por intento | {_s(tk['bruto_r'])} | {_s(mk['bruto_r'])} |",
        f"| Costo en R por intento | {_f(tk['costo_r'])} | {_f(mk['costo_r'])} |",
        f"| · comisiones | {_f(tk['comision_r'])} | {_f(mk['comision_r'])} |",
        f"| · deslizamiento | {_f(tk['desliz_r'])} | {_f(mk['desliz_r'])} |",
        f"| · funding | {_s(tk['funding_r'])} | {_s(mk['funding_r'])} |",
        "",
        f"**ΔE[R] neto por intento (maker − taker): {_s(d['delta'])} R**, IC95 % bootstrap "
        f"emparejado [{_s(d['lo'])}, {_s(d['hi'])}], n = {d['n']}."
        + ("  \n**El intervalo incluye 0: la diferencia no es distinguible del ruido.**"
           if d["lo"] <= 0 <= d["hi"] else ""),
        "",
        "### Cuánto de esto era el denominador",
        "",
        "Con el riesgo **realizado** —el que usa el motor— las mismas operaciones dan "
        f"{_s(tk['neto_r_realizado'])} R (taker) y {_s(mk['neto_r_realizado'])} R (maker), "
        f"es decir ΔE[R] {_s(mk['neto_r_realizado'] - tk['neto_r_realizado'])} R. "
        f"El riesgo medio realizado es {tk['riesgo_medio'] * 100:.3f} % del precio en taker y "
        f"{mk['riesgo_medio'] * 100:.3f} % en maker. "
        + ("La diferencia entre las dos lecturas es la inflación aritmética que el denominador "
           "común elimina."
           if abs(mk["riesgo_medio"] - tk["riesgo_medio"]) > 1e-9 else
           "Los dos riesgos coinciden, así que aquí el denominador no inflaba nada."),
        "",
        "## 3. Lectura B, descriptiva: lo que se consigue cuando se consigue",
        "",
        "Solo sobre las operaciones que existieron en cada brazo. **No decide**: los denominadores "
        "no son el mismo.",
        "",
        "| | taker | maker |",
        "|---|--:|--:|",
        f"| n | {tk['llenadas']} | {mk['llenadas']} |",
        f"| E[R] neto por llenada | {_s(tk['neto_r_llenada'])} | {_s(mk['neto_r_llenada'])} |",
        f"| Costo en R por llenada | {_f(tk['costo_r_llenada'])} | {_f(mk['costo_r_llenada'])} |",
        f"| Acierto | {tk['acierto_pct']:.1f} % | {mk['acierto_pct']:.1f} % |",
        f"| Factor de beneficio | {_f(tk['pf'], 3)} | {_f(mk['pf'], 3)} |",
        "",
        "## 4. Estabilidad",
        "",
        "### Los tres plazos de la rejilla",
        "",
        "| `fill_h` | Llenado | Costo R taker | Costo R maker | ΔE[R] neto | IC95 % |",
        "|---|--:|--:|--:|--:|---|",
    ]
    for k, g in r["grid"].items():
        gd = g["delta"]
        mark = " **(decide)**" if float(k) == r["decide_bars"] else ""
        out.append(f"| {k} vela{'s' if float(k) != 1 else ''}{mark} | "
                   f"{g['maker']['llenado_pct']:.1f} % | {_f(g['taker']['costo_r'])} | "
                   f"{_f(g['maker']['costo_r'])} | {_s(gd['delta'])} | "
                   f"[{_s(gd['lo'])}, {_s(gd['hi'])}] |")
    out += ["", "### Año a año (plazo que decide)", "",
            "| Año | n | ΔE[R] neto por intento |", "|---|--:|--:|"]
    for y, s in r["por_anio"].items():
        out.append(f"| {y} | {s['n']} | {_s(s['delta'])} |")
    out += _stress_section(r) + _shadow_section(r) + _live_section(r) + _limits(r)
    return "\n".join(out)


def _stress_line(r: dict) -> str:
    st = r.get("estres") or {}
    if not st:
        return ""
    bad = [k for k, s in st.items() if not s["veredicto"]["adopta"]]
    if not bad:
        return ("**El veredicto aguanta el estrés de cola** en todos los niveles probados (§5): "
                "exigir que el precio pase del nivel no lo cambia.")
    return (f"**El veredicto NO aguanta el estrés de cola** a {', '.join(bad)} pb (§5): si la "
            "orden solo se llena cuando el precio pasa del nivel, deja de cumplir el criterio. "
            "**Esto manda sobre §1**: el llenado del motor es optimista por construcción.")


def _stress_section(r: dict) -> list[str]:
    st = r.get("estres") or {}
    if not st:
        return []
    out = ["", "## 5. Estrés de cola: ¿y si hay que pasar del nivel, no solo tocarlo?", "",
           "`_limit_fill` del motor da la orden por llenada cuando la vela **toca** el precio. Una "
           "orden en reposo necesita que el precio la **atraviese**, o estar al frente de la cola; "
           "medir eso de verdad es T79, y hasta entonces la hipótesis del motor es la optimista. "
           "Aquí se exige que el nivel se pase en `n` puntos básicos. **Solo puede empeorar a "
           "maker**, y por eso se añade aunque no estuviera en el pre-registro.", "",
           "| Paso exigido | Llenado | Costo R maker | ΔE[R] neto | IC95 % | ¿Adopta? |",
           "|---|--:|--:|--:|---|---|"]
    for k, s in st.items():
        d = s["delta"]
        out.append(f"| {k} pb | {s['maker']['llenado_pct']:.1f} % | "
                   f"{_f(s['maker']['costo_r'])} | {_s(d['delta'])} | "
                   f"[{_s(d['lo'])}, {_s(d['hi'])}] | "
                   f"{'sí' if s['veredicto']['adopta'] else '**no**'} |")
    return out


def _shadow_section(r: dict) -> list[str]:
    sh = r.get("sombra") or {}
    if not sh:
        return []
    return [
        "", "## 6. Lectura secundaria: con «una viva por estrategia» (descriptiva)", "",
        "Con la regla real del libro los dos brazos **dejan de ver las mismas decisiones**: si la "
        "límite no se llena, la estrategia queda libre antes y toma otras. Por eso no decide; "
        "enseña qué le pasaría al libro.", "",
        "| | taker | maker |", "|---|--:|--:|",
        f"| Operaciones | {sh['taker'].get('llenadas', 0)} | {sh['maker'].get('llenadas', 0)} |",
        f"| E[R] neto por intento | {_s(sh['taker'].get('neto_r'))} | "
        f"{_s(sh['maker'].get('neto_r'))} |",
        f"| Costo en R por intento | {_f(sh['taker'].get('costo_r'))} | "
        f"{_f(sh['maker'].get('costo_r'))} |",
    ]


def _live_section(r: dict) -> list[str]:
    lv = r.get("libro_vivo") or {}
    if not lv:
        return []
    out = ["", "## 7. Control de realidad en el libro vivo (confundido, no es evidencia)", "",
           "Cada estrategia elige su tipo de orden, así que esto **no compara iguales**: sirve "
           "para ver que los órdenes de magnitud cuadran, nada más.", "",
           "| Tipo | n | E[R] neto | Costo R | Acierto |", "|---|--:|--:|--:|--:|"]
    for kind, s in lv.items():
        out.append(f"| `{kind}` | {s['n']} | {_s(s['neto_r'])} | {_f(s['costo_r'])} | "
                   f"{s['acierto_pct']:.1f} % |")
    return out


def _limits(r: dict) -> list[str]:
    return [
        "", "## 8. Lo que esta medición no cubre", "",
        f"- **No hay 15 m.** El banco de T131 se pre-registró con marcos "
        f"{', '.join(r['marcos'])} y no tiene ni una operación de 15 m, que es donde el stop está "
        "más cerca y el costo más pesa (T136 §1). Esta medición **no dice nada** de ese marco.",
        f"- **El camino de precios es de {r['path_tf']}.** Dentro de una vela no se sabe el orden "
        "de los extremos, así que el llenado es el que el motor supone, igual en los dos brazos.",
        "- **No mide ventaja.** Si el bruto se mueve, no es porque se prediga mejor.",
        "- **Adoptar maker cambia la huella de versión** de todas las estrategias afectadas "
        "(`versioning.py`) y reinicia la cuenta de operaciones en vivo de V5. Es ◆ del usuario.",
        "",
    ]


def write_csv(path: Path, r: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lectura", "fill_h_velas", "paso_pb", "brazo", "intentos", "llenadas",
                    "llenado_pct", "neto_r", "bruto_r", "costo_r", "comision_r", "desliz_r",
                    "acierto_pct", "pf"])
        for k, g in r["grid"].items():
            for arm in ("taker", "maker"):
                w.writerow(["rejilla", k, 0, arm, *_row(g[arm])])
        for k, s in (r.get("estres") or {}).items():
            w.writerow(["estres", f"{r['decide_bars']:g}", k, "maker", *_row(s["maker"])])


def _row(s: dict) -> list:
    return [s["intentos"], s["llenadas"], f"{s['llenado_pct']:.2f}", f"{s['neto_r']:.6f}",
            f"{s['bruto_r']:.6f}", f"{s['costo_r']:.6f}", f"{s['comision_r']:.6f}",
            f"{s['desliz_r']:.6f}", f"{s['acierto_pct']:.2f}",
            "" if s["pf"] is None else f"{s['pf']:.4f}"]
