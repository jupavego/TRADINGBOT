"""Informe de T54: lo que afirma cada libro frente a lo observado en BTC, y el ajuste de escenarios.

Entra el payload de la puerta T49 (`Validator.compute`), las operaciones sombra por ficha y el
resultado de `tilt_eval.evaluate_tilt`; sale Markdown + JSON. Si nada pasa, lo dice y lista qué
falla.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from eim.paper.engine import Outcome
from eim.validation.lineage import Version, out_of_sample, tuning_windows
from eim.validation.stats import day_block_ci, rng_for

FAMILY = "literatura"
BOOT = 5000
LEVEL = 0.95
OBS = {"alcista": "sube", "bajista": "baja", "giro": "se invierte", "continuacion": "continúa"}


def _d(t: int | None, fmt: str = "%Y-%m-%d") -> str:
    return "—" if not t else datetime.fromtimestamp(t / 1000, UTC).strftime(fmt)


def _f(x: float | None, fmt: str = "+.3f") -> str:
    return "—" if x is None else format(x, fmt)


def card_of(o: Outcome) -> str:
    """La ficha que originó la idea (`key` = `ficha:t`)."""
    return o.idea.key.split(":")[0]


def trades_by_card(outcomes: Iterable[Outcome], current: Mapping[str, Version],
                   allv: Sequence[Version], symbol: str, asof: int
                   ) -> dict[str, list[tuple[int, float, str]]]:
    """`{ficha: [(decisión, R neto, marco)]}` con el mismo criterio de la puerta: operaciones
    CERRADAS de la versión vigente, en `exit_t ≤ asof` y fuera de toda ventana de ajuste."""
    wins = {sid: tuning_windows(v, [x for x in allv if x.sid == sid])
            for sid, v in current.items()}
    out: dict[str, list[tuple[int, float, str]]] = defaultdict(list)
    for o in outcomes:
        i = o.idea
        v = current.get(i.sid)
        if (i.family != FAMILY or v is None or i.version != v.fingerprint
                or o.status != "CERRADA" or o.r is None or (o.exit_t or 0) > asof
                or not out_of_sample(i.t, symbol, wins[i.sid])):
            continue
        out[card_of(o)].append((i.t, float(o.r), i.timeframe))
    return out


def card_stats(trades: Sequence[tuple[int, float, str]], label: str) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "mean_r": None, "ci": [None, None], "win": None,
                "verdict": "sin operaciones"}
    t = np.array([x[0] for x in trades], dtype=np.int64)
    r = np.array([x[1] for x in trades], dtype=float)
    lo, hi = day_block_ci(r, t, BOOT, LEVEL, rng_for(0, f"lit_card|{label}"))
    mean = float(r.mean())
    if not (math.isfinite(lo) and math.isfinite(hi)):     # n = 1: sin intervalo, no «nan»
        return {"n": n, "mean_r": mean, "ci": [None, None], "win": float((r > 0).mean()),
                "verdict": "no hay muestra para juzgar"}
    word = ("no hay muestra para juzgar" if n < 30 else "positivo (IC95 % sobre 0)" if lo > 0
            else "negativo (IC95 % bajo 0)" if hi < 0 else "no distinguible de 0")
    return {"n": n, "mean_r": mean, "ci": [lo, hi], "win": float((r > 0).mean()), "verdict": word}


def _claims(claims: Mapping[str, dict]) -> list[str]:
    out = ["| Ficha | Cita | Lo que afirma el autor | Evidencia que da el autor |",
           "|---|---|---|---|"]
    for cid, c in sorted(claims.items()):
        out.append(f"| `{cid}` | {c['cite']} | {c['claim']} | {c['evidence']} |")
    return out


def _by_card(rows: Mapping[str, dict], claims: Mapping[str, dict]) -> list[str]:
    out = ["| Ficha | Op. FdM | R medio neto [IC95 %] | Acierto | Lectura |",
           "|---|---|---|---|---|"]
    for cid in sorted(claims):
        s = rows.get(cid) or card_stats([], cid)
        out.append(f"| `{cid}` | {s['n']} | {_f(s['mean_r'])} [{_f(s['ci'][0])}, "
                   f"{_f(s['ci'][1])}] | {_f(s['win'], '.1%')} | {s['verdict']} |")
    return out


def _versions(vs: Sequence[dict]) -> list[str]:
    out = ["| Versión | Veredicto T49 | FdM | R medio [IC95 %] | p → Holm | Falla |",
           "|---|---|---|---|---|---|"]
    for v in sorted(vs, key=lambda x: x["id"]):
        ck = {c["id"]: c for c in v["checks"]}
        ci = ck["V2"]["value"]["ci"]
        v3 = ck["V3"]["value"]
        bad = " ".join(c["id"] for c in v["checks"] if c["ok"] is False) or "—"
        out.append(f"| `{v['id']}` | **{v['verdict']}** | {v['n_oos']} | {_f(v['mean_r'])} "
                   f"[{_f(ci[0])}, {_f(ci[1])}] | {_f(v3['p'], '.4f')} → {_f(v3['p_holm'], '.4f')}"
                   f" | {bad} |")
    return out


def _tilt(t: dict) -> list[str]:
    if not t:
        return ["No se calculó (sin velas de BTCUSDT 1 h en el almacén)."]
    out = [f"`{t['version']}` · k = {t['k']} · {t['n']} pronósticos "
           f"({t['n_active']} con neto ≠ 0) · desde {_d(t.get('span', [None])[0])} hasta "
           f"{_d(t.get('span', [None, None])[-1])} · **{t['verdict']}** — {t['reason']}.", ""]
    if t.get("checks"):
        out += ["| ID | Criterio | Observado | Umbral | |", "|---|---|---|---|---|"]
        out += [f"| {c['id']} | {c['name']} | {c['value']} | {c['threshold']} | "
                f"{'✔' if c['ok'] else '✘'} |" for c in t["checks"]]
        b, ll = t["brier"], t["logloss"]
        out += ["", f"Brier base {b['base']:.5f} → ajustado {b['tilt']:.5f}; log-loss base "
                f"{ll['base']:.5f} → ajustado {ll['tilt']:.5f} (piso de probabilidad "
                f"{t['log_floor']:g} en ambos).", "",
                "Curva de calibración (predicha → observada, 3 clases juntas):", "",
                "| Intervalo | Base p̂ → obs (n) | Ajustado p̂ → obs (n) |", "|---|---|---|"]
        for a, c in zip(t["curve"]["base"], t["curve"]["tilt"], strict=False):
            out.append(f"| {a['p_pred']:.2f} / {c['p_pred']:.2f} | {a['p_pred']:.3f} → "
                       f"{a['p_obs']:.3f} ({a['n']}) | {c['p_pred']:.3f} → {c['p_obs']:.3f} "
                       f"({c['n']}) |")
    return out


def conclusion(vs: Sequence[dict], tilt: dict) -> list[str]:
    val = [v["id"] for v in vs if v["verdict"] == "VALIDADA"]
    fails: dict[str, int] = defaultdict(int)
    for v in vs:
        for c in v["checks"]:
            if c["ok"] is False:
                fails[f"{c['id']} {c['name']}"] += 1
    out = [f"**{len(val)} de {len(vs)}** versiones de la familia `literatura` VALIDADAS"
           + (": " + ", ".join(f"`{x}`" for x in val) + "." if val else
              ": ninguna regla de libro tiene hoy evidencia fuera de muestra suficiente en "
              "BTCUSDT.")]
    if fails and not val:
        out.append("Qué falla más a menudo: " + "; ".join(
            f"{k} ({n})" for k, n in sorted(fails.items(), key=lambda kv: -kv[1])) + ".")
    verdict = (tilt or {}).get("verdict", "no calculado")
    out.append(f"Ajuste de escenarios: **{verdict}** — "
               + ("queda APAGADO (`enabled: false`)." if verdict != "ACEPTA" else
                  "cumple los criterios; encenderlo es una decisión del usuario (commit)."))
    return out


def build(validation: dict, by_card: Mapping[str, list], claims: Mapping[str, dict],
          tilt: dict, meta: dict) -> dict:
    vs = [v for v in validation["verdicts"] if v["strategy"].startswith("lit_")]
    cards = {cid: card_stats(tr, cid) for cid, tr in by_card.items()}
    return {"meta": meta, "claims": dict(claims), "versions": vs, "by_card": cards, "tilt": tilt,
            "conclusion": conclusion(vs, tilt), "attempts": validation.get("attempts"),
            "criteria": validation["criteria"]["version"]}


def render(r: dict) -> str:
    m, vs = r["meta"], r["versions"]
    return "\n".join([
        f"# T54 — Retroalimentación con evidencia (`lit_v1`, {m['date']})", "",
        f"Modo: **SIMULADO** · símbolo {m['symbol']} · preregistro "
        f"`PLAN/notas/T54_preregistro.md` (commit `{m.get('prereg_commit') or 'ver git log'}`) · "
        f"criterios `{r['criteria']}` · intentos registrados {r['attempts']} · datos hasta "
        f"{_d(m.get('asof'), '%Y-%m-%d %H:%M')} UTC.", "",
        "## 1. Resultado", "", *[f"- {x}" for x in r["conclusion"]], "",
        "## 2. Lo que afirma cada libro", "", *_claims(r["claims"]), "",
        "## 3. Lo observado en BTCUSDT (fuera de muestra, neto de costos)", "",
        "Por estrategia@marco@versión (veredicto de la puerta T49, criterios sin tocar):", "",
        *_versions(vs), "", "Por ficha (los pares espejo se separan aquí):", "",
        *_by_card(r["by_card"], r["claims"]), "",
        "## 4. Ajuste de las probabilidades de escenario", "", *_tilt(r["tilt"]), "",
        "## 5. Notas", "", *[f"- {n}" for n in m.get("notes", [])], ""])


def write(r: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"lit_v1_{r['meta']['date']}"
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"
    md.write_text(render(r), encoding="utf-8")
    js.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return md, js
