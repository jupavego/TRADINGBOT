"""Pasada del diario de la protección (T110): compara lo recalculado con lo guardado y escribe una
fila por cambio.

Corre tras recalcular la vista de un símbolo, con el `Journal` leído ANTES de simular (el suelo ya
entró en la simulación). Reglas, por operación de origen `vivo` con escalera:
- Nueva → «alta» y una fila por cada cambio del stop ya ocurrido; «cierre» si ya cerró.
- Con fila vigente abierta → una fila por cada SL nuevo MEJOR que el guardado, en orden, y
  «cierre» si cerró. Si el suelo subió el SL recalculado (el recálculo quedó por debajo), una fila
  «recuperacion» y aviso: se adoptó el guardado. Al arrancar, si el recálculo va por delante de lo
  guardado, se adopta el recálculo (el mayor de los dos) y también se avisa.
- Estado inconsistente (instantánea ausente o corrupta, que no cuadra, cierre antes de lo guardado,
  velas que no llegan, operación guardada que el recálculo no encuentra, guardada cerrada pero
  abierta al recalcular) → una fila «inconsistente» y el diario de esa operación queda congelado
  (ni cambios ni cierre) hasta reconciliarla a mano (`reconcile`).
Ninguna fila automática deja el SL por debajo del guardado (`_never_lower`). Y nada que dependa de
una vela de 15 m sin sus velas de 1 min se guarda todavía (T142, `protection_settle`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from eim.data.paper_store import PaperStore
from eim.paper.book import ProfileState
from eim.paper.engine import Path
from eim.paper.params import ExecParams
from eim.paper.protection import (
    COLS,
    HELD,
    MISSING,
    OPEN,
    Journal,
    append,
    history,
    problem,
    split,
    write_pass,
)
from eim.paper.protection_ops import Cur, current_ops
from eim.paper.protection_settle import Ready, gate, settled

EPS = 1e-9
GONE = "la operación guardada no aparece al recalcular: no se puede reconstruir con seguridad"
DECISIONS = {"recalculo": "reconciliada", "descartar": "descartada"}


@dataclass
class PassResult:
    symbol: str
    first_ms: int
    rows: list[dict] = field(default_factory=list)
    held: dict[str, str] = field(default_factory=dict)     # op_id → motivo, vigentes al terminar
    recovered: list[dict] = field(default_factory=list)    # recálculo < guardado: se adoptó éste
    ahead: list[dict] = field(default_factory=list)        # al arrancar, recálculo > guardado
    open_ids: set[str] = field(default_factory=set)
    waiting: list[str] = field(default_factory=list)       # a la espera de velas de 1 min (T142)


def _state_now(c: Cur) -> dict:
    hist = c.info["stop_history"]
    last = hist[-1] if hist else None
    # «activa» = el stop ya protege. Un arrastre adaptativo puede moverse sin cruzar la entrada
    return {"active": c.info.get("active", bool(hist)), "level": c.info["level"],
            "stop": c.info["stop"],
            "max_float_usd": c.info["max_float_usd"],
            "protected_usd": last["nominal"] if last else None,
            "stop_source": c.info["stop_source"], "updated_t": last["t"] if last else c.fill_t}


def _state_at(h: dict) -> dict:
    return {"active": h.get("active", True), "level": h["level"], "stop": h["stop"],
            "max_float_usd": h["max_float"], "protected_usd": h["nominal"],
            "stop_source": h["source"], "updated_t": h["t"]}


def _state_alta(c: Cur) -> dict:
    return {"active": False, "level": 0, "stop": c.initial_sl, "max_float_usd": None,
            "protected_usd": None, "stop_source": "inicial", "updated_t": c.fill_t}


def _row(c: Cur, seq: int, event: str, state: dict, hist: list, now: int, note: str = "",
         status: str | None = None, close: dict | None = None) -> dict:
    status = status or ("cerrada" if close else "protegida" if state["active"] else "abierta")
    return {"row_id": f"{c.op_id}|{seq}", "op_id": c.op_id, "seq": seq, "event": event,
            "profile": c.profile, "symbol": c.symbol, "idea_id": c.idea_id, "side": c.side,
            "entry": c.entry, "qty": c.qty, "notional": c.qty * c.entry,
            "initial_sl": c.initial_sl, "first_usd": c.info["first_usd"],
            "step_usd": c.info["step_usd"], **state,
            "costs": json.dumps(c.costs, default=str), "status": status,
            "history": json.dumps(hist, default=str),
            "close_reason": close["reason"] if close else None,
            "exit_t": close["exit_t"] if close else None,
            "exit_price": close["exit"] if close else None, "note": note, "recorded_ms": now}


def _copy(saved: dict, seq: int, event: str, status: str, note: str, now: int) -> dict:
    return {**saved, "row_id": f"{saved['op_id']}|{seq}", "seq": seq, "event": event,
            "status": status, "note": note, "recorded_ms": now}


def _held(op_id: str, seq: int, why: str, now: int, saved: dict | None, c: Cur | None) -> dict:
    """Fila «inconsistente»: copia lo guardado si se puede leer (su stop no se toca); si no, el
    estado recalculado; si tampoco hay, solo la identidad de la operación."""
    if saved is not None and (c is None or not problem(saved)):
        return _copy(saved, seq, "inconsistente", HELD, why, now)
    if c is not None:
        return _row(c, seq, "inconsistente", _state_now(c), c.info["stop_history"], now, why, HELD)
    ids = split(op_id) or ("", "", "")
    base = dict.fromkeys(COLS) | {"op_id": op_id, "profile": ids[0], "symbol": ids[1],
                                  "idea_id": ids[2], "history": "[]"}
    return _copy(base, seq, "inconsistente", HELD, why, now)


def _why_held(j: Journal, op_id: str, c: Cur | None, saved: dict | None) -> str:
    if saved is None:
        return MISSING if op_id in j.prev_open else ""
    if op_id in j.problems:
        return f"instantánea corrupta: {j.problems[op_id]}"
    if saved["status"] in OPEN:
        if c is None:
            return GONE
        if c.info.get("inconsistent"):
            return c.info["inconsistent"]
    if saved["status"] == "cerrada" and c is not None and c.close is None:
        return (f"guardada como cerrada ({saved.get('close_reason')}) pero el recálculo la ve "
                "abierta")
    return ""


def _fresh(c: Cur, seq: int, now: int, note: str) -> list[dict]:
    """Alta, una fila por cada cambio del stop y el cierre (operación sin estado vigente)."""
    hist = [h for h in c.info["stop_history"] if h["source"] != "recuperado"]
    rows = [_row(c, seq, "alta", _state_alta(c), [], now, note)]
    for n, h in enumerate(hist, 1):
        rows.append(_row(c, seq + n, "escalon", _state_at(h), hist[:n], now))
    if c.close:
        rows.append(_row(c, seq + len(hist) + 1, "cierre", _state_now(c), hist, now,
                         close=c.close))
    return rows


def _never_lower(rows: list[dict], saved: dict) -> bool:
    return all((r["stop"] - saved["stop"]) * saved["side"] >= -EPS for r in rows)


def plan(j: Journal, ops: dict[str, Cur], now: int, *, startup: bool = False,
         seen: set[str] | None = None, ready: Ready | None = None) -> PassResult:
    """Qué escribir y qué avisar en esta pasada (puro: no toca la base). `ready` dice qué instantes
    ya no pueden cambiar con velas de 1 min que falten (T142); None, todos."""
    seen = set() if seen is None else seen
    res = PassResult(j.symbol, j.first_ms or now)
    for op_id in sorted(set(ops) | set(j.latest)):
        c, saved = ops.get(op_id), j.latest.get(op_id)
        seq = int(saved["seq"]) + 1 if saved and isinstance(saved.get("seq"), int) else 1
        if saved is not None and saved.get("status") == HELD:
            res.held[op_id] = saved.get("note") or HELD     # congelada hasta reconciliarla
            continue
        if why := _why_held(j, op_id, c, saved):
            res.rows.append(_held(op_id, seq, why, now, saved, c))
            res.held[op_id] = why
            continue
        status = saved["status"] if saved else None
        if status in ("cerrada", "descartada") or c is None:
            if status == "reconciliada" and c is None:
                res.rows.append(_copy(saved, seq, "reconciliada", "descartada",
                                      "el recálculo ya no tiene la operación", now))
            continue
        if status is None and c.close is not None and c.fill_t < res.first_ms:
            continue                                        # cerrada antes de que hubiera diario
        c, waits = settled(c, ready)
        if waits:
            res.waiting.append(op_id)
        if status in (None, "reconciliada"):
            note = ("reanudada desde el recálculo tras la reconciliación" if status
                    else "" if j.first_ms else "el diario empieza con la operación ya abierta")
            res.rows += _fresh(c, seq, now, note)
        else:
            res.rows += _follow(c, saved, seq, now, startup, seen, res)
        if c.close is None:
            res.open_ids.add(op_id)
    res.open_ids |= set(res.held)
    return res


def _follow(c: Cur, saved: dict, seq: int, now: int, startup: bool, seen: set[str],
            res: PassResult) -> list[dict]:
    """Operación con estado vigente abierto y válido: recuperación, cambios nuevos y cierre."""
    rows: list[dict] = []
    hist = json.loads(saved["history"])
    rec = c.info.get("recovered")
    if rec:
        note = (f"el recálculo daba escalón {rec['from_level']} (SL {rec['from_stop']:g}) y lo "
                f"guardado escalón {rec['saved_level']} (SL {rec['to_stop']:g}): se adopta el "
                "guardado")
        if saved.get("event") != "recuperacion":
            rows.append(_copy(saved, seq, "recuperacion", saved["status"], note, now))
        if c.op_id not in seen:
            seen.add(c.op_id)
            res.recovered.append({"op_id": c.op_id, **rec, "note": note})
    ref, new = saved["stop"], []
    for h in c.info["stop_history"]:
        if h["source"] != "recuperado" and (h["stop"] - ref) * c.side > EPS:
            new.append(h)
            ref = h["stop"]
    for h in new:
        hist = [*hist, h]
        rows.append(_row(c, seq + len(rows), "escalon", _state_at(h), hist, now))
    if startup and new and not rec:
        res.ahead.append({"op_id": c.op_id, "from_level": saved["level"],
                          "to_level": c.info["level"], "changes": len(new),
                          "from_stop": saved["stop"], "to_stop": new[-1]["stop"]})
    if c.close:
        rows.append(_row(c, seq + len(rows), "cierre", _state_now(c), hist, now, close=c.close))
    if not _never_lower(rows, saved):          # salvaguarda: ninguna ruta automática baja el SL
        res.held[c.op_id] = "el recálculo bajaría el stop guardado"
        return [_copy(saved, seq, "inconsistente", HELD, res.held[c.op_id], now)]
    return rows


def run_pass(pstore: PaperStore, j: Journal, books: dict[str, ProfileState], ep: ExecParams,
             now: int, *, startup: bool = False, seen: set[str] | None = None,
             fine: Path | None = None) -> PassResult:
    """Pasada completa: decide, escribe las filas nuevas y recuerda qué quedó abierto. `fine` son
    las velas de 1 min con las que se simuló: lo que dependa de las que faltan, espera (T142)."""
    res = plan(j, current_ops(j.symbol, books, ep), now, startup=startup, seen=seen,
               ready=gate(fine, ep))
    append(pstore, res.rows)
    if j.first_ms is None or res.open_ids != j.prev_open:    # solo si cambió
        write_pass(pstore, j.symbol, res.first_ms, now, res.open_ids)
    return res


def reconcile(pstore: PaperStore, op_id: str, decision: str, note: str, now: int) -> dict:
    """Resolución manual de una operación en estado inconsistente (deja la nota en el diario).

    - `recalculo`: el recálculo pasa a mandar; la siguiente pasada reanuda el diario desde él (o
      la descarta si ya no existe). Única vía que puede dejar un SL guardado atrás, y solo por
      decisión explícita y anotada.
    - `descartar`: el diario deja de seguirla.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decisión desconocida «{decision}» (válidas: {sorted(DECISIONS)})")
    note = (note or "").strip()
    if len(note) < 3:
        raise ValueError("la nota es obligatoria: explica por qué se resuelve así")
    rows = history(pstore, op_id)
    if not rows:
        raise LookupError(f"el diario no tiene la operación {op_id}")
    last = rows[-1]
    if last["status"] != HELD:
        raise ValueError(f"solo se reconcilia una operación en estado inconsistente "
                         f"(estado vigente: {last['status']})")
    row = _copy(last, int(last["seq"]) + 1, "reconciliada", DECISIONS[decision],
                f"reconciliada a mano ({decision}): {note}", now)
    append(pstore, [row])
    return row
