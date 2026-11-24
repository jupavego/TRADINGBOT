"""Informe del patrón de apertura (T211): acumula cada apertura y la mide contra el pre-registro.

    python -m eim.analytics.apertura_report                     # desde la fecha del pre-registro
    python -m eim.analytics.apertura_report --desde 2026-11-24  # ventana explícita
    python -m eim.analytics.apertura_report --linea-base <parquet de 1m>   # rehacer la base

Cada apertura medida se guarda una sola vez en `data/apertura/aperturas.jsonl` (append-only, con
su huella de pre-registro): así la muestra hacia delante sobrevive a la poda del almacén de 1 m.
Por eso solo se guardan las aperturas cuya ventana de 4 h ya cerró: una fila escrita a medias no
se podría completar después, y el registro se quedaría sin la variante candidata en las plazas
que abren poco antes de la corrida.
El informe sale en `reports/apertura/` y el resumen en `latest.json`. Solo lee el almacén; no
toca el libro de T31, ni la cantera, ni la síntesis.
Salida: 0 = informe escrito; 2 = no se pudo leer el almacén o el pre-registro.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from eim.analytics import apertura as A

MIN_MS = 60_000
N_PARA_POTENCIA = 30    # por debajo de esto, la sd no da para estimar cuánta muestra falta


def _ms(fecha: str) -> int:
    """Fecha ISO a ms epoch. Sin zona explícita se entiende UTC, no la hora del equipo."""
    d = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return int(d.timestamp() * 1000)


def _dia(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def medir(bars: A.Bars, pr: dict, desde_ms: int) -> tuple[list[dict], int]:
    """Una fila por apertura con las tres variantes. Devuelve (filas, aplazadas).

    Solo se miden las aperturas cuya ventana ya cerró: una apertura de hace menos de 4 h
    daría canales vacíos por falta de vela, y el registro es append-only, así que esa fila a
    medias se quedaría para siempre. Las aplazadas se miden enteras en la corrida siguiente.
    """
    k = int(pr["k"])
    cm = float(pr["costes_bps"]["mercado_ida_vuelta"])
    cl = float(pr["costes_bps"]["limite_ida_vuelta"])
    filas: list[dict] = []
    aplazadas = 0
    for z in pr["zonas"]:
        for i0 in A.opens(bars, z["tz"], int(z["hh"]), int(z["mm"])):
            if bars.t[i0] < desde_ms:
                continue
            if not A.ventana_cerrada(bars, int(i0), k):
                aplazadas += 1
                continue
            fila = {"zona": z["id"], "t": int(bars.t[i0]), "dia": _dia(int(bars.t[i0]))}
            op = A.contra_a(bars, int(i0), k, 3, cm)
            if op is None:
                continue
            fila["a_bps"] = round(op["a_bps"], 3)
            fila["contra_a_3m"] = round(op["neto_bps"], 3)
            fila["contra_a_3m_bruto"] = round(op["bruto_bps"], 3)
            fila["sentido"] = op["sentido"]
            for modo, nombre in (("rebote", "canal_rebote"), ("ruptura", "canal_ruptura")):
                r = A.canal_op(bars, int(i0), k, modo, A.VENTANA_LLENADO, A.TOPE_MIN, cl)
                if r is None:
                    fila[nombre] = None
                elif not r["lleno"]:
                    fila[nombre] = None
                    fila[f"{nombre}_sin_llenar"] = "ambigua" if r["ambigua"] else "no_toco"
                    fila["ancho_bps"] = round(r["ancho_bps"], 2)
                else:
                    fila[nombre] = round(r["neto_bps"], 3)
                    fila[f"{nombre}_bruto"] = round(r["bruto_bps"], 3)
                    fila[f"{nombre}_motivo"] = r["motivo"]
                    fila["ancho_bps"] = round(r["ancho_bps"], 2)
            filas.append(fila)
    return sorted(filas, key=lambda f: (f["t"], f["zona"])), aplazadas


def acumular(path: Path, filas: list[dict], sha: str) -> tuple[int, int]:
    """Añade al registro las aperturas que no estuvieran ya. Devuelve (nuevas, total)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    vistas: set[tuple[str, int]] = set()
    total = 0
    if path.exists():
        for linea in path.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            vistas.add((d.get("zona", ""), int(d.get("t", 0))))
            total += 1
    nuevas = [f for f in filas if (f["zona"], f["t"]) not in vistas]
    if nuevas:
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            for f in nuevas:
                fh.write(json.dumps({**f, "prereg": sha[:12]}, ensure_ascii=False) + "\n")
    return len(nuevas), total + len(nuevas)


def leer_registro(path: Path, desde_ms: int) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if int(d.get("t", 0)) >= desde_ms:
            out.append(d)
    return out


def resumir(filas: list[dict], pr: dict) -> dict:
    """Resumen por variante y zona, más la agrupada y el veredicto de la candidata."""
    out: dict = {"por_variante": {}}
    reglas = pr["regla_de_veredicto"]
    for v in pr["variantes"]:
        vid = v["id"]
        por_zona = {}
        for z in pr["zonas"]:
            xs = [f[vid] for f in filas if f["zona"] == z["id"] and f.get(vid) is not None]
            s = A.resumen(xs)
            if s["n"]:
                base = (pr["linea_base_2024_2026"].get(vid) or {}).get(z["id"], {})
                s["linea_base_bruto_bps"] = base.get("bruto_bps")
                s["n_minima"] = reglas["n_minima_por_zona"].get(z["id"])
            por_zona[z["id"]] = s
        agr = A.resumen([f[vid] for f in filas if f.get(vid) is not None])
        if agr["n"]:
            agr["n_minima"] = reglas["n_minima_agrupada"]
            # Con poquísimas operaciones la sd no vale para estimar potencia: la cifra saldría
            # ridícula (un puñado de aperturas «bastarían»), que es lo contrario de la verdad.
            agr["n_necesaria_con_lo_medido"] = round(
                A.n_necesaria(agr["sd_bps"], agr["media_bps"]), 0) \
                if agr["sd_bps"] and agr["n"] >= N_PARA_POTENCIA else None
        out["por_variante"][vid] = {"papel": v["papel"], "por_zona": por_zona, "agrupada": agr}
    cand = next((v["id"] for v in pr["variantes"] if v["papel"] == "candidatura"), None)
    if cand:
        agr = out["por_variante"][cand]["agrupada"]
        out["veredicto"] = A.veredicto(
            agr, {"n_minima": reglas["n_minima_agrupada"]}, float(reglas["umbral_t"])) \
            if agr.get("n") else (f"sin veredicto: ninguna de las {len(filas)} aperturas medidas "
                                  f"dejó una operación de {cand}")
        out["candidata"] = cand
    return out


def render(res: dict, pr: dict, filas: list[dict], total: int, nuevas: int,
           aplazadas: int = 0) -> str:
    L = [f"# Patrón de apertura — informe de seguimiento ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
         "",
         f"Pre-registro `{pr['version']}` (huella `{pr['sha256'][:12]}`, abierto {pr['abierto']}).",
         f"Muestra hacia delante desde {pr['reloj']['muestra_hacia_delante_desde']}; "
         f"veredicto no antes de {pr['reloj']['veredicto_no_antes_de']}.",
         f"Registro acumulado: {total} aperturas ({nuevas} nuevas en esta corrida). "
         f"En la ventana: {len(filas)}."
         + (f" Aplazadas a la corrida siguiente, por no haber cerrado aún sus 4 h: "
            f"{aplazadas}." if aplazadas else ""),
         "", f"**{res.get('veredicto', 'sin veredicto')}**", ""]
    for vid, d in res["por_variante"].items():
        L += [f"## {vid} ({d['papel']})", "",
              "| zona | n | media neta | mediana | sd | t | aciertos | base 2024-26 (bruto) | n mínima |",
              "|---|---|---|---|---|---|---|---|---|"]
        for z, s in d["por_zona"].items():
            if not s.get("n"):
                L.append(f"| {z} | 0 | — | — | — | — | — | — | — |")
                continue
            base = s.get("linea_base_bruto_bps")
            L.append(f"| {z} | {s['n']} | {s['media_bps']:+.2f} | {s['mediana_bps']:+.2f} | "
                     f"{s['sd_bps']:.1f} | {s['t']:+.2f} | {s['aciertos_pct']:.1f} % | "
                     f"{'—' if base is None else f'{base:+.2f}'} | {s.get('n_minima', '—')} |")
        a = d["agrupada"]
        if a.get("n"):
            nn = a.get("n_necesaria_con_lo_medido")
            potencia = (f"para que una media de {a['media_bps']:+.2f} bps con esta sd fuese "
                        f"significativa harían falta {nn:.0f} aperturas") if nn is not None else (
                       f"con n = {a['n']} la desviación todavía no permite estimar cuánta "
                       f"muestra haría falta")
            L += ["", f"Agrupada: n = {a['n']}, media {a['media_bps']:+.2f} bps, t = {a['t']:+.2f}, "
                      f"acumulado {a['total_bps'] / 100:+.2f} %. Mínima para veredicto: "
                      f"{a.get('n_minima')}; {potencia}.", ""]
    L += ["## Límites declarados en el pre-registro", ""] + \
         [f"- {x}" for x in pr["limites_declarados"]] + [""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="reports/apertura")
    ap.add_argument("--desde", default=None, help="YYYY-MM-DD; por defecto, la del pre-registro")
    ap.add_argument("--prereg", default=A.DEFAULT_VERSION)
    ap.add_argument("--symbol", default=None)
    a = ap.parse_args(argv)
    try:
        pr = A.load_prereg(a.prereg)
    except (OSError, ValueError) as exc:
        print(f"ERROR: pre-registro: {exc}")
        return 2
    desde_ms = _ms(a.desde) if a.desde else _ms(pr["reloj"]["muestra_hacia_delante_desde"])

    from eim.data.store import Store
    store = Store(Path(a.data_dir))
    sym = a.symbol or pr["symbol"]
    try:
        candles = store.read_candles(sym, pr["timeframe"], start=desde_ms - 10 * MIN_MS)
    except (OSError, ValueError) as exc:
        print(f"ERROR: almacén: {exc}")
        return 2
    if not candles:
        # Distinguir «la ventana aún no ha empezado» de «el almacén no responde»: la primera es
        # el estado normal hasta que la muestra arranca, y no debe parecer una avería.
        try:
            ultimas = store.read_candles(sym, pr["timeframe"], last=1)
        except (OSError, ValueError):
            ultimas = []
        if not ultimas:
            print(f"ERROR: el almacén no tiene velas de {sym} {pr['timeframe']}")
            return 2
        print(f"Sin muestra todavía: la última vela de {sym} es de {_dia(ultimas[-1].t)} y la "
              f"ventana empieza el {_dia(desde_ms)}. Nada que medir; no se escribe informe.")
        return 0
    bars = A.bars_from_candles(candles)
    filas, aplazadas = medir(bars, pr, desde_ms)
    reg = Path(a.data_dir) / "apertura" / "aperturas.jsonl"
    nuevas, total = acumular(reg, filas, pr["sha256"])
    todas = leer_registro(reg, desde_ms)
    res = resumir(todas, pr)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    texto = render(res, pr, todas, total, nuevas, aplazadas)
    nombre = f"apertura_{datetime.now(UTC):%Y%m%d}.md"
    (out / nombre).write_text(texto, encoding="utf-8", newline="\n")
    (out / "latest.json").write_text(
        json.dumps({"asof": datetime.now(UTC).isoformat(), "prereg": pr["sha256"][:12],
                    "registro": str(reg), "n_total": total, "n_nuevas": nuevas,
                    "n_ventana": len(todas), "n_aplazadas": aplazadas, **res},
                   ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    print(f"{out / nombre}: {len(todas)} aperturas en la ventana ({nuevas} nuevas, "
          f"{total} en el registro, {aplazadas} aplazadas). "
          f"{res.get('veredicto', 'sin veredicto')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
