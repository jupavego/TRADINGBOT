"""Las cifras del informe mensual de la cantera (T172, entregable 1). Puras y descriptivas.

En la mirada que fijan el pre-registro `cantera_v1` y la nota de T167 §10: rentabilidad neta por
prospecto frente al azar (sus gemelos pareados) y frente a comprar y mantener; qué teoría se
sostiene por agente y **por tema** (efectos aleatorios con estimaciones encogidas, `themes.py`);
lo nativo frente al genérico (Holm sobre los agentes); N efectivo frente al nominal;
persistencia del orden; PBO como descriptivo y volatilidad y drawdown como señal temprana
(rec. 7, 9, 10, 14, 15 y 17). **Nada de aquí asciende ni da de baja a nadie**: eso lo hace solo
el escalafón en sus revisiones fijadas.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from scipy import stats as sps

from eim.nursery import themes
from eim.nursery.ladder import Standing
from eim.nursery.ladder_final import daily_d, n_effective
from eim.nursery.ladder_stats import DAY_MS, AccountData
from eim.nursery.report.rows import Snapshot, account_metrics
from eim.paper.exits.stats import pbo

ALPHA_SECONDARY = 0.10          # capa sensible del pre-registro (temas y nativo frente a genérico)
EARLY_DD_SHARE = 0.5            # drawdown ≥ la mitad de su tope: se vigila (no decide nada)
EARLY_VOL_X = 2.0               # volatilidad diaria ≥ 2 × la mediana de la familia: se vigila


def prospect_rows(snap: Snapshot, stand: Mapping[str, Standing]) -> list[dict]:
    """Una fila por prospecto del pre-registro, en su orden, con su etapa y su motivo."""
    acc_of, bh = snap.account_of(), (snap.buy_hold or {}).get("return_pct")
    caps = snap.prereg.ladder.drawdown.caps_pct
    out = []
    for x in snap.prereg.family.members:
        k = account_metrics(snap, acc_of.get(x.id, ""))
        s = stand.get(x.id)
        out.append({
            "id": x.id, "agent": x.agent_id, "theme": x.theme, "timeframe": x.timeframe,
            "band": s.band if s else x.band, "role": x.role,
            "stage": s.stage if s else "guarderia", "promoted": bool(s and s.frozen_e is not None),
            "exit": s.exit if s else None, **k,
            "vs_buy_hold_pp": None if bh is None else round(k["net_return_pct"] - bh, 3),
            "dd_cap_pct": caps.get(x.id),
            "evalue": (s.metrics.get("evalue") if s else None),
            "futility_ub": (s.metrics.get("futility_ub") if s else None),
        })
    return out


def _d_by(snap: Snapshot, data: Mapping[str, AccountData]) -> dict[str, list[float]]:
    acc_of = snap.account_of()
    return {x.id: [c.d for c in data.get(acc_of.get(x.id, ""), AccountData()).closed]
            for x in snap.prereg.family.members}


def theories(snap: Snapshot, data: Mapping[str, AccountData]) -> dict:
    """Qué teoría se sostiene: por tema (Holm) y por agente, con medias encogidas al tema."""
    pr = snap.prereg
    clip = pr.ladder.primary.clip_r
    d_by = _d_by(snap, data)
    theme_of = {x.id: x.theme for x in pr.family.members}
    shrunk = themes.shrink(d_by, theme_of, clip)
    by_theme = themes.theme_tests(d_by, theme_of, clip, ALPHA_SECONDARY)
    agents: dict[str, dict] = {}
    for x in pr.family.members:
        a = agents.setdefault(x.agent_id, {"prospects": [], "d": []})
        a["prospects"].append({"id": x.id, "theme": x.theme, **shrunk.get(x.id, {})})
        a["d"].extend(np.clip(d_by[x.id], -clip, clip).tolist())
    for a in agents.values():
        d = np.asarray(a.pop("d"), float)
        if len(d) >= 2:
            h = 1.96 * float(d.std(ddof=1)) / np.sqrt(len(d))
            a.update(n=int(len(d)), d_mean=round(float(d.mean()), 4),
                     lo=round(float(d.mean()) - h, 4), hi=round(float(d.mean()) + h, 4))
        else:
            a.update(n=int(len(d)), d_mean=None, lo=None, hi=None)
    return {"by_theme": by_theme, "by_agent": agents, "shrunk": shrunk, "clip_r": clip}


def native_vs_generic(snap: Snapshot, data: Mapping[str, AccountData]) -> dict:
    """Por agente con prospectos: d de los suyos frente al de su `agente_{id}` genérico (Holm)."""
    pr = snap.prereg
    d_by = _d_by(snap, data)
    native: dict[str, list[float]] = {}
    generic: dict[str, list[float]] = {}
    seen: set[str] = set()
    for x in pr.family.members:
        native.setdefault(x.agent_id, []).extend(d_by[x.id])
        if x.generic not in seen:
            seen.add(x.generic)
            generic.setdefault(x.agent_id, []).extend(
                c.d for c in data.get(x.generic, AccountData()).closed)
    res = themes.native_vs_generic(native, generic, ALPHA_SECONDARY)
    for a in res:
        res[a]["n_native"], res[a]["n_generic"] = len(native[a]), len(generic.get(a, ()))
    return {"agents": res, "tests": len(res), "alpha": ALPHA_SECONDARY}


def _daily_matrix(snap: Snapshot, data: Mapping[str, AccountData]) -> tuple[list[str], np.ndarray]:
    acc_of = snap.account_of()
    ids, cols = [], []
    for x in snap.prereg.family.members:
        acc = data.get(acc_of.get(x.id, ""), AccountData())
        if acc.closed:
            ids.append(x.id)
            cols.append(daily_d(acc, snap.alta_ms, snap.asof_ms))
    if not cols:
        return [], np.zeros((0, 0))
    return ids, np.column_stack(cols)


def family_shape(snap: Snapshot, data: Mapping[str, AccountData]) -> dict:
    """N efectivo frente al nominal, persistencia del orden y PBO (descriptivo)."""
    pr = snap.prereg
    ids, mat = _daily_matrix(snap, data)
    neff = n_effective(mat, pr.ladder.first_team.neff_corr) if len(ids) else None
    return {"m_nominal": pr.m, "members": len(pr.family.members), "with_trades": len(ids),
            "n_effective": neff, "neff_corr": pr.ladder.first_team.neff_corr,
            "persistence": persistence(snap, data), "pbo": _pbo(ids, mat)}


def persistence(snap: Snapshot, data: Mapping[str, AccountData]) -> dict:
    """¿Se mantiene el orden? Media de d en la primera y la segunda mitad de lo transcurrido.

    Descriptivo: la regla que decide (meses 1–3 frente a 4–6) solo se aplica en la mirada final.
    """
    min_n = snap.prereg.ladder.first_team.persistence_min_trades
    cut = snap.alta_ms + (snap.asof_ms - snap.alta_ms) // 2
    a, b = [], []
    for ds in _halves(snap, data, cut).values():
        if len(ds[0]) >= min_n and len(ds[1]) >= min_n:
            a.append(float(np.mean(ds[0])))
            b.append(float(np.mean(ds[1])))
    if len(a) < 3:
        return {"prospects": len(a), "spearman": None, "min_trades": min_n,
                "reason": f"hacen falta ≥ 3 prospectos con ≥ {min_n} cierres en cada mitad"}
    rho = sps.spearmanr(a, b)
    ma = float(np.median(a))
    top = [j for j, v in enumerate(a) if v > ma]
    keep = sum(1 for j in top if b[j] > float(np.median(b)))
    return {"prospects": len(a), "spearman": round(float(rho.statistic), 3),
            "p": round(float(rho.pvalue), 4), "top_half_kept": f"{keep}/{len(top)}",
            "min_trades": min_n, "cut_ms": cut}


def _halves(snap: Snapshot, data: Mapping[str, AccountData], cut: int
            ) -> dict[str, tuple[list[float], list[float]]]:
    acc_of = snap.account_of()
    out = {}
    for x in snap.prereg.family.members:
        cs = data.get(acc_of.get(x.id, ""), AccountData()).closed
        out[x.id] = ([c.d for c in cs if c.exit_t < cut], [c.d for c in cs if c.exit_t >= cut])
    return out


def _pbo(ids: list[str], mat: np.ndarray, splits: int = 8) -> dict:
    """PBO/CSCV sobre tramos de días iguales (descriptivo, rec. 9: no decide)."""
    if len(ids) < 2 or mat.shape[0] < 2 * splits:
        return {"pbo": None, "reason": f"hacen falta ≥ 2 prospectos con cierres y "
                                       f"≥ {2 * splits} días (hay {len(ids)} y {mat.shape[0]})"}
    parts = np.array_split(np.arange(mat.shape[0]), 2 * splits)
    matrix = {pid: [float(mat[p, j].sum()) for p in parts] for j, pid in enumerate(ids)}
    out = pbo(matrix, splits=splits)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def early_signals(rows: list[dict]) -> list[dict]:
    """Volatilidad y drawdown como señal temprana (rec. 17): se vigila, no se decide."""
    vols = [r["daily_vol_pct"] for r in rows if r.get("daily_vol_pct") and r["n"] > 0]
    med = float(np.median(vols)) if vols else None
    out = []
    for r in rows:
        why = []
        cap = r.get("dd_cap_pct")
        if cap and r["max_dd_pct"] >= EARLY_DD_SHARE * cap:
            why.append(f"drawdown {r['max_dd_pct']:.1f} % (≥ {EARLY_DD_SHARE:.0%} de su tope "
                       f"{cap:.1f} %)")
        v = r.get("daily_vol_pct")
        if med and v and r["n"] > 0 and v >= EARLY_VOL_X * med:
            why.append(f"volatilidad diaria {v:.2f} % (≥ {EARLY_VOL_X:g} × la mediana "
                       f"{med:.2f} %)")
        if why and r["stage"] != "baja":
            out.append({"id": r["id"], "why": why})
    return out


def auto_adapt_events(snap: Snapshot) -> list[dict]:
    """Eventos de `AUTO_ADAPT` del libro (puerta de costo por marco), en orden de hora."""
    return sorted(snap.events, key=lambda e: int(e.get("t") or 0))


def elapsed_days(snap: Snapshot) -> float:
    return round((snap.asof_ms - snap.alta_ms) / DAY_MS, 2)
