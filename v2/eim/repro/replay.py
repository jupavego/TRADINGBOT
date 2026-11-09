"""`repetir` (T124): recalcula un resultado contra su instantánea y, si no coincide, dice por qué.

Base = datos de la instantánea + parámetros grabados + código de hoy. Las tres causas se separan
cambiando un solo factor respecto de esa base:
- **código**: la base no da la cifra grabada (datos y parámetros son los mismos de entonces);
- **datos**: la copia congelada ya no da su hash, o el almacén de hoy ya no tiene lo que fijó la
  instantánea y con lo que tiene la cifra cambia;
- **parámetros**: los vigentes no son los grabados y con ellos la cifra cambia.
**Se repite** solo si la base y el cálculo de hoy (datos, código y parámetros de hoy) dan
exactamente las cifras grabadas. Los tipos sin recálculo (`kinds.KINDS`) solo comprueban datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from eim.data import revisions
from eim.data.results import ResultRecord, ResultStore
from eim.data.snapshots import Snapshot, SnapshotCorrupt, SnapshotInfo, SnapshotStore, content_hash
from eim.data.store import Store
from eim.repro.code import describe, fingerprint
from eim.repro.kinds import KINDS, changed_keys, compare
from eim.repro.text import data_lines, figure_lines

OK, FAIL, DATA_ONLY = "se_repite", "no_se_repite", "solo_datos"


@dataclass
class DataState:
    info: SnapshotInfo
    intact: bool | None = None          # None = ligera (sin copia que comprobar)
    error: str = ""
    store_same: bool = True
    diff: dict = field(default_factory=dict)
    snap: Snapshot | None = None        # datos de la instantánea (copia o almacén con su hash)
    live: Snapshot | None = None


@dataclass
class Check:
    result: ResultRecord
    verdict: str
    causes: list[str]
    lines: list[str]
    detail: dict

    @property
    def exit_code(self) -> int:
        return 0 if self.verdict in (OK, DATA_ONLY) and not self.causes else 1


def _row_diff(a: Snapshot, b: Snapshot, noted: set[int]) -> dict:
    """Velas cambiadas, que faltan o que sobran en `b` respecto de `a`, y funding distinto."""
    ka, kb = {c.t: c for c in a.candles}, {c.t: c for c in b.candles}
    changed = sorted(t for t in ka.keys() & kb.keys() if ka[t] != kb[t])
    out = {"changed": changed, "missing": sorted(ka.keys() - kb.keys()),
           "added": sorted(kb.keys() - ka.keys()),
           "funding_changed": len(set(a.funding) ^ set(b.funding)),
           "noted": sorted(set(changed) & noted)}
    out["examples"] = [{"t": t, "before": ka[t].model_dump(), "after": kb[t].model_dump()}
                       for t in changed[:3]]
    return out


def data_state(sstore: SnapshotStore, store, info: SnapshotInfo) -> DataState:
    st = DataState(info)
    if info.frozen:
        try:
            st.snap, st.intact = sstore.load(info.id), True
        except SnapshotCorrupt as exc:
            st.intact, st.error = False, str(exc)
    st.live = sstore.live(store, info)
    st.store_same = content_hash(st.live.candles, st.live.funding) == info.content_hash
    if st.store_same and st.snap is None:
        st.snap = st.live                  # el almacén aún tiene exactamente sus datos (hash)
    if not st.store_same:
        revs = revisions.read(sstore.root, since_ms=info.created_ms, symbol=info.symbol)
        noted = {r["t"] for r in revs if revisions.touches(r, info)}
        st.diff = (_row_diff(st.snap, st.live, noted) if st.snap is not None
                   else {"noted": sorted(noted)})
    return st


def repetir(root: str | Path, rid: str, store=None, kinds=KINDS, save: bool = True) -> Check:
    """`store`: almacén con que comparar; por defecto, el de cada instantánea (o `root`)."""
    rstore, sstore = ResultStore(root), SnapshotStore(root)
    rec = rstore.get(rid)
    if rec is None:
        raise KeyError(f"resultado desconocido: {rid}")
    infos = [sstore.get(s) for s in rec.snapshots]
    if not infos or any(i is None for i in infos):
        raise KeyError(f"{rid}: sin instantánea registrada ({rec.snapshots}): no reproducible")
    states = [data_state(sstore, store or Store(Path(root) / (i.store_dir or ".")), i)
              for i in infos]
    kind = kinds.get(rec.kind)
    now = fingerprint()
    lines = [f"Resultado {rec.id} · {rec.kind} · {rec.name}"] + data_lines(states)
    lines.append(f"Código: grabado {describe(rec.code)} · hoy {describe(now)}")
    broken = any(s.intact is False for s in states)
    drift = any(not s.store_same for s in states)
    causes: list[str] = ["datos"] if broken or (drift and kind and kind.recompute is None) else []
    figs: dict = {}
    if kind is None or kind.recompute is None:
        why = kind.why_not if kind else f"tipo {rec.kind!r} sin recálculo"
        lines.append(f"Sin recálculo: {why}.")
        verdict = DATA_ONLY
    else:
        verdict, extra = _recompute(kind, rec, states, figs, lines)
        causes += [c for c in extra if c not in causes]
    lines.append("VEREDICTO: " + {OK: "SE REPITE", FAIL: "NO SE REPITE",
                                  DATA_ONLY: "SOLO DATOS"}[verdict]
                 + (f" · causas: {', '.join(c.upper() for c in causes)}" if causes else ""))
    detail = {"figures": figs, "code_now": now,
              "data": [{"id": s.info.id, "intact": s.intact, "store_same": s.store_same,
                        "error": s.error, "diff": s.diff} for s in states]}
    check = Check(rec, verdict, causes, lines, detail)
    if save:
        rstore.add_check(rid, verdict, causes, detail)
    return check


def _safe(kind, data: list[Snapshot], params: dict) -> dict:
    """Un recálculo que falla es una cifra que no sale: se anota el error y se atribuye."""
    try:
        return kind.recompute(data, params)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _recompute(kind, rec: ResultRecord, states: list[DataState], figs: dict,
               lines: list[str]) -> tuple[str, list[str]]:
    base_data = [s.snap for s in states]
    base_ok = all(d is not None for d in base_data)
    today_data = [s.live for s in states]
    drift = any(not s.store_same for s in states)
    p0, p1 = rec.params, kind.current(rec.params)
    moved = changed_keys(p0, p1)
    if base_ok:
        figs["base"] = _safe(kind, base_data, p0)
    if drift:
        figs["datos"] = _safe(kind, today_data, p0)
    if moved and base_ok:
        figs["parametros"] = _safe(kind, base_data, p1)
    if drift and moved:
        figs["hoy"] = _safe(kind, today_data, p1)
    elif drift:
        figs["hoy"] = figs["datos"]
    elif moved and base_ok:
        figs["hoy"] = figs["parametros"]
    else:
        figs["hoy"] = figs["base"] if base_ok and not moved else _safe(kind, today_data, p1)
    causes = []
    if base_ok and compare(rec.figures, figs["base"]):
        causes.append("código")
    if drift and (not base_ok or compare(figs["base"], figs["datos"])):
        causes.append("datos")
    if moved and (not base_ok or compare(figs["base"], figs["parametros"])):
        causes.append("parámetros")
    lines.append("Parámetros: " + (f"cambiaron {', '.join(moved)}" if moved
                                    else "los vigentes son los grabados"))
    lines += figure_lines(rec.figures, figs, base_ok)
    lines += [f"Error al recalcular ({k}): {v['error']}" for k, v in figs.items() if "error" in v]
    intact = all(s.intact is not False for s in states)
    same = base_ok and intact and not compare(rec.figures, figs["base"]) and \
        not compare(rec.figures, figs["hoy"])
    if not same and not causes and intact:
        lines.append("Ninguna causa sola cambia la cifra: cambia al combinarlas.")
    return (OK if same else FAIL), causes
