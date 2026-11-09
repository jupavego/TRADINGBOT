"""Textos de `repetir` (T124): estado de los datos y comparación de cifras, en castellano."""

from __future__ import annotations

from datetime import UTC, datetime

from eim.repro.kinds import compare


def ts(ms: int | None) -> str:
    if ms is None:
        return "—"
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _n(x) -> str:
    return f"{x:,}".replace(",", " ") if isinstance(x, int) else str(x)


def data_lines(states: list) -> list[str]:
    out = []
    for s in states:
        i, cov = s.info, s.info.coverage()
        kind = "congelada" if i.frozen else "ligera (sin copia)"
        body = (f"{_n(i.n_candles)} velas de {_n(cov['expected'])}, {i.gaps} huecos"
                if i.kind != "funding" else "solo funding")
        out.append(f"Instantánea {i.id} · {kind} · {i.symbol} {i.timeframe} · {ts(i.start_ms)} → "
                   f"{ts(i.end_ms)} · {body} · {_n(i.n_funding)} de funding · {i.source} · "
                   f"creada {ts(i.created_ms)}")
        if s.intact is False:
            out.append(f"  copia congelada ALTERADA: {s.error}")
        elif s.intact:
            out.append("  copia congelada íntegra (hash coincide)")
        if s.store_same:
            out.append("  almacén de hoy: idéntico a la instantánea")
            continue
        d = s.diff
        if "changed" in d:
            noted = len(d["noted"])
            out.append(f"  almacén de hoy: DISTINTO · {len(d['changed'])} velas cambiadas "
                       f"({noted} anotadas como revisión, {len(d['changed']) - noted} sin anotar), "
                       f"{len(d['missing'])} faltan, {len(d['added'])} nuevas, "
                       f"{d['funding_changed']} filas de funding distintas")
            for e in d["examples"]:
                b, a = e["before"], e["after"]
                moved = [k for k in ("o", "h", "l", "c", "v") if b[k] != a[k]]
                out.append(f"    vela {ts(e['t'])}: " + ", ".join(
                    f"{k} {b[k]!r} → {a[k]!r}" for k in moved))
        else:
            out.append(f"  almacén de hoy: DISTINTO (hash); {len(d.get('noted', []))} revisiones "
                       "anotadas en el rango desde que se creó")
    return out


def figure_lines(recorded: dict, figs: dict, base_ok: bool) -> list[str]:
    out = []
    if not base_ok:
        out.append("Sin datos de la instantánea: no se puede separar el efecto del código.")
    else:
        bad = compare(recorded, figs["base"])
        out.append(f"Contra la instantánea ({len(recorded)} cifras): " +
                   ("todas iguales, exactas" if not bad else f"{len(bad)} distintas"))
        out += [f"  {d['figure']}: grabado {d['recorded']!r} · hoy {d['now']!r}" for d in bad]
    for name, title in (("datos", "con los datos de hoy"),
                        ("parametros", "con los parámetros vigentes")):
        if name in figs and base_ok:
            bad = compare(figs["base"], figs[name])
            out.append(f"Recalculado {title}: " + ("misma cifra" if not bad else
                       "cambia " + ", ".join(f"{d['figure']} {d['recorded']!r} → {d['now']!r}"
                                             for d in bad)))
    bad = compare(recorded, figs["hoy"])
    out.append("Hoy (datos, código y parámetros de hoy): " + (
        "coincide con lo grabado" if not bad else f"{len(bad)} cifras distintas de lo grabado"))
    return out
