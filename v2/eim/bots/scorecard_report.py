"""Informe de la puntuación de bots (T59): `reports/bots_scorecard.md` + `.json`, tal cual salga."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[2] / "reports"
MARK = {True: "✔", False: "✘", None: "…"}


def _ts(ms: int | None) -> str:
    return "—" if ms is None else datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def _f(x, k: int = 3) -> str:
    return "—" if x is None else f"{x:+.{k}f}"


def _bot_section(b: dict) -> list[str]:
    ex = b["verdict"]["extras"]
    out = [f"\n### {b['id']}\n", *[f"- {r}" for r in b["reasons"]],
           f"- Puerta: **{b['verdict']['verdict']}** — {b['verdict']['reason']}"]
    out += [f"  - {c['id']} {c['name']} {MARK[c['ok']]}: {c['reason']}"
            for c in b["verdict"]["checks"]]
    out.append(f"- Comparación homogénea: buy&hold del mismo tramo {_f(ex.get('buy_hold'))} · "
               f"control aleatorio R medio {_f(b['control']['mean_r'])} · "
               f"retorno con 1 % de riesgo {_f(ex.get('ret_1pct'))}.")
    if b["marginal"]:
        m = b["marginal"]
        out.append(f"- Aporte marginal: {m['reason']} · deltas {m['deltas']} · "
                   f"moderador {m['moderator']}")
    return out


def _source(m: dict | None) -> list[str]:
    if not m:
        return []
    return [f"Medido en la máquina `{m['machine']}` sobre la base `{m['data_dir']}`: solo vale "
            "para la API que lea esa misma base.\n"]


def _frames(frames: list[dict]) -> list[str]:
    """Qué leyó la puntuación de cada marco (T119): posturas y hasta dónde llegan sus velas."""
    if not frames:
        return []
    out = ["## Marcos leídos\n", "| Marco | Posturas | Desde | Hasta | Velas del camino | "
           "Velas hasta | Fija el corte |", "|---|---|---|---|---|---|---|"]
    out += [f"| {f['timeframe']} | {f['signals']} | {_ts(f['first_signal'])} | "
            f"{_ts(f['last_signal'])} | {f['path_tf']} | {_ts(f['candles_to'])} | "
            f"{'sí' if f['sets_asof'] else 'no'} |" for f in frames]
    return [*out, ""]


def render(p: dict) -> str:
    s = p["summary"]
    lines = [
        "# Escuadrón de bots — puntuación y puerta de edge (T59)\n",
        f"Modo: **{p['mode']}** · símbolo {p['symbol']} · corte (asof) {_ts(p.get('asof'))} UTC · "
        f"criterios `{p['criteria']['version']}` (sha {p['criteria']['sha256'][:12]}) · "
        f"intentos en la familia de Holm: {p['attempts_total']} (cada versión de cada bot, "
        "también las retiradas, más un control aleatorio por cada una).\n",
        *_source(p.get("measured_on")),
        "## Respuesta corta\n",
        f"- **Votan**: {', '.join(s['votan']) or 'ninguno'}",
        f"- **Solo informan**: {', '.join(s['informan']) or 'ninguno'}",
        f"- **Publicables** (VALIDADOS por T49): {', '.join(s['publicables']) or 'ninguno'}",
        f"- **Modulan la confianza**: {', '.join(s['modulan_confianza']) or 'ninguno'}",
        f"- Estados: {s['states']}\n",
        "> " + p["windows_note"] + "\n",
        *_frames(p.get("frames", [])),
        "## Concepto por bot (cuatro dimensiones, sin nota global)\n",
        "| Bot@estrategia@marco@versión | Estado | Rendimiento | Evidencia | Seguridad | "
        "Operativa | R medio | n OOS | p Holm | Control (R medio) | Peso inicial |",
        "|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in p["bots"]:
        d, v, c = b["dimensions"], b["verdict"], b["control"]
        lines.append(
            f"| {b['id']} | **{b['state']}** | {d['rendimiento']['estado']} | "
            f"{d['evidencia']['estado']} | {d['seguridad']['estado']} | "
            f"{d['operativa']['estado']} | {_f(v['mean_r'])} | {v['n_oos']} | "
            f"{_f(v['p_holm'], 4)} | {_f(c['mean_r'])} | {b['initial_weight']} |")
    for b in p["bots"]:
        lines += _bot_section(b)
    r = p["regimes"]
    lines += ["\n## Condiciones por régimen (solo informe)\n",
              f"{r['note']}. Celdas bot×régimen evaluadas: {r['attempts']}.\n",
              "| Bot | Régimen | n OOS | Evaluada | Supera | R medio | p Holm |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {x['id']} | {x['regime']} | {x['n_oos']} | {x['evaluated']} | {x['passes']} | "
              f"{_f(x['mean_r'])} | {_f(x['p_holm'], 4)} |" for x in r["rows"]]
    lines.append("\n## Clase L (simulación aparte; no vota ni pasa por la puerta direccional)\n")
    if not p["lane_l"]:
        lines.append("Sin corridas guardadas.")
    lines += [f"- {x['id']} ({x['version'][:12]}): {x['fills']} fills · PnL de inventario "
              f"{_f(x['pnl_inventory'], 2)} · costos pagados {_f(x['costs_paid'], 2)} · "
              f"DD máx {_f(x['max_drawdown'])} · riesgo de inventario {x['inventory_risk']} "
              f"— {x['note']}" for x in p["lane_l"]]
    lines += ["\n## Todos los intentos (Holm)\n",
              "| Intento | Veredicto | n OOS | p bruto | p Holm | Retirado | Control |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {a['id']} | {a['verdict']} | {a['n_oos']} | {_f(a['p_raw'], 4)} | "
              f"{_f(a['p_holm'], 4)} | {a['retired']} | {a['control']} |" for a in p["attempts"]]
    return "\n".join(lines) + "\n"


def write(p: dict, out: Path | None = None) -> tuple[Path, Path]:
    out = out or REPORTS
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / "bots_scorecard.md", out / "bots_scorecard.json"
    md.write_text(render(p), encoding="utf-8")
    js.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return md, js
