"""Unión del registro de versiones de la puerta de validación (T49) entre máquinas (T61).

`n` es un contador que asigna cada máquina, así que no sirve de identidad: la identidad de una
versión es `(sid, huella)`. Al importar se reasignan `n` y `parent` locales (los `n` ya
existentes no cambian, por eso los veredictos locales siguen siendo válidos). Las ventanas de
ajuste se UNEN: más ventanas = más datos descartados de «fuera de muestra», nunca menos. Las
versiones importadas entran retiradas (la vigente la decide el código de esta máquina).
Todos los intentos cuentan para Holm: la unión de intentos = la unión de huellas.
"""

from __future__ import annotations

from dataclasses import dataclass

from eim.data.share_merge import lit as _lit

VCOLS = ("sid", "n", "fingerprint", "strategy", "timeframe", "created_ms", "parent", "origin",
         "note", "retired_ms")


@dataclass
class Counts:
    new: int = 0
    dup: int = 0
    incompatible: int = 0


def merge_versions(con, vfile, wfile, src: str, import_id: str, now_ms: int
                   ) -> tuple[Counts, Counts]:
    """Une `val_versions` y `val_windows` exportadas (`vfile`, `wfile`: Parquet o listas de
    partes) en `con`."""
    incoming = con.execute(f"SELECT {', '.join(VCOLS)} FROM read_parquet({_lit(vfile)}) "
                           "ORDER BY sid, n").fetchall()
    local = {(r[0], r[1]): int(r[2]) for r in con.execute(
        "SELECT sid, fingerprint, n FROM val_versions").fetchall()}
    top: dict[str, int] = {}
    for (sid, _), n in local.items():
        top[sid] = max(top.get(sid, 0), n)
    mapped: dict[tuple[str, int], int] = {}
    v, origin = Counts(), []
    for sid, n, fp, strat, tf, created, parent, org, note, retired in incoming:
        if (sid, fp) in local:
            mapped[(sid, int(n))] = local[(sid, fp)]
            v.dup += 1
            continue
        top[sid] = top.get(sid, 0) + 1
        local[(sid, fp)] = mapped[(sid, int(n))] = top[sid]
        con.execute("INSERT INTO val_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [sid, top[sid], fp, strat, tf, created,
                     None if parent is None else mapped.get((sid, int(parent))), org, note,
                     retired if retired is not None else now_ms])
        origin.append(("val_versions", f"{sid}|{fp}", src, import_id))
        v.new += 1
    have = {(r[0], int(r[1]), r[2], r[3], r[4], r[5]) for r in con.execute(
        "SELECT sid, n, from_ms, to_ms, symbol, note FROM val_windows").fetchall()}
    fp_at = {(s, k): f for (s, f), k in local.items()}
    w = Counts()
    for sid, n, a, b, sym, note in con.execute(
            f"SELECT sid, n, from_ms, to_ms, symbol, note FROM read_parquet({_lit(wfile)}) "
            "ORDER BY sid, n, from_ms, to_ms").fetchall():
        ln = mapped.get((sid, int(n)))
        if ln is None:
            w.incompatible += 1
            continue
        row = (sid, ln, a, b, sym, note)
        if row in have:
            w.dup += 1
            continue
        have.add(row)
        con.execute("INSERT INTO val_windows VALUES (?,?,?,?,?,?)", list(row))
        fp = fp_at[(sid, ln)]
        origin.append(("val_windows", f"{sid}|{fp}|{a}|{b}|{sym}|{note}", src, import_id))
        w.new += 1
    if origin:
        con.executemany("INSERT INTO share_origin VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                        origin)
    return v, w
