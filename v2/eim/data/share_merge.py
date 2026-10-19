"""Unión idempotente de una tabla exportada con la local (T61): nuevas / ya presentes /
en conflicto / incompatibles. Todo en SQL sobre la conexión de la base destino.

- Identidad = clave natural (`Spec.key`). Mismas claves y mismo contenido (sin las columnas
  volátiles, que son tiempos locales) → «ya presente». Mismas claves y contenido distinto →
  CONFLICTO: se conserva lo local, se registra en `share_conflicts` y se informa.
- `counter` (bitácora con `seq` local): se une por contenido y se reasigna `seq` tras el máximo
  local de cada líder.
- Cada fila nueva queda en `share_origin` (máquina de origen).
"""

from __future__ import annotations

from dataclasses import dataclass

from eim.data.share_spec import Spec


@dataclass
class Result:
    tbl: str
    src: str
    new: int = 0
    dup: int = 0
    conflict: int = 0
    incompatible: int = 0
    note: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)


def lit(path) -> str:
    return "'" + str(path).replace("\\", "/").replace("'", "''") + "'"


def q(c: str) -> str:
    return '"' + c + '"'


def local_columns(con, table: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = "
        "current_database() AND table_name = ? ORDER BY column_index", [table]).fetchall()]


def _key_str(sp: Spec, alias: str) -> str:
    return "concat_ws('|', " + ", ".join(f"CAST({alias}.{q(k)} AS VARCHAR)" for k in sp.key) + ")"


def merge_table(con, sp: Spec, file, columns: list[list], src: str, import_id: str) -> Result:
    """Une `file` (Parquet con `columns` = [[nombre, tipo]…]) en la tabla local `sp.name`."""
    res = Result(sp.name, src)
    got = [(c, t) for c, t in columns]
    have = local_columns(con, sp.name)
    n_in = con.execute(f"SELECT count(*) FROM read_parquet({lit(file)})").fetchone()[0]
    if got != have:
        res.incompatible, res.note = int(n_in), "columnas distintas de las locales"
        return res
    names = [c for c, _ in have]
    cmp_cols = [c for c in names if c not in sp.key and c not in sp.volatile]
    km = " AND ".join(f"t.{q(k)} = i.{q(k)}" for k in sp.key)
    eq = " AND ".join(f"t.{q(c)} IS NOT DISTINCT FROM i.{q(c)}" for c in cmp_cols) or "TRUE"
    order = ", ".join(q(c) for c in names)
    part = ", ".join(q(k) for k in sp.key)
    con.execute(f"CREATE OR REPLACE TEMP TABLE inc AS SELECT * FROM read_parquet({lit(file)}) "
                f"QUALIFY row_number() OVER (PARTITION BY {part} ORDER BY {order}) = 1")
    tbl = q(sp.name)
    if sp.kind == "counter":
        return _merge_counter(con, sp, res, names, km, tbl, import_id)
    new, dup, conf = con.execute(
        "SELECT count(*) FILTER (WHERE NOT hk), count(*) FILTER (WHERE hk AND heq), "
        "count(*) FILTER (WHERE hk AND NOT heq) FROM ("
        f"SELECT EXISTS (SELECT 1 FROM {tbl} t WHERE {km}) hk, "
        f"EXISTS (SELECT 1 FROM {tbl} t WHERE {km} AND {eq}) heq FROM inc i)").fetchone()
    res.new, res.dup, res.conflict = int(new), int(dup), int(conf)
    if conf:
        differs = " || ".join(
            f"CASE WHEN t.{q(c)} IS DISTINCT FROM i.{q(c)} THEN '{c} ' ELSE '' END"
            for c in cmp_cols) or "''"
        con.execute(
            "INSERT INTO share_conflicts SELECT ?, ?, " + _key_str(sp, "i") + ", ?, "
            f"{differs}, to_json(i) FROM inc i JOIN {tbl} t ON {km} WHERE NOT EXISTS "
            f"(SELECT 1 FROM {tbl} t2 WHERE {km.replace('t.', 't2.')} AND "
            f"{eq.replace('t.', 't2.')}) QUALIFY row_number() OVER "
            "(PARTITION BY " + _key_str(sp, "i") + ") = 1", [import_id, sp.name, src])
    if new:
        absent = f"NOT EXISTS (SELECT 1 FROM {tbl} t WHERE {km})"
        con.execute("INSERT INTO share_origin SELECT ?, " + _key_str(sp, "i") + ", ?, ? "
                    f"FROM inc i WHERE {absent} ON CONFLICT DO NOTHING",
                    [sp.name, src, import_id])
        con.execute(f"INSERT INTO {tbl} ({', '.join(q(c) for c in names)}) "
                    f"SELECT {', '.join('i.' + q(c) for c in names)} FROM inc i WHERE {absent}")
    return res


def _merge_counter(con, sp: Spec, res: Result, names: list[str], km: str, tbl: str,
                   import_id: str) -> Result:
    absent = f"NOT EXISTS (SELECT 1 FROM {tbl} t WHERE {km})"
    res.dup = int(con.execute(f"SELECT count(*) FROM inc i WHERE NOT ({absent})").fetchone()[0])
    con.execute(
        "CREATE OR REPLACE TEMP TABLE newj AS SELECT i.*, row_number() OVER "
        f"(PARTITION BY i.leader_id ORDER BY i.t, i.seq) AS rn FROM inc i WHERE {absent}")
    res.new = int(con.execute("SELECT count(*) FROM newj").fetchone()[0])
    if res.new:
        seq = (f"(coalesce((SELECT max(x.seq) FROM {tbl} x WHERE x.leader_id = n.leader_id), 0)"
               " + n.rn)")
        sel = ", ".join(f'{seq} AS "seq"' if c == "seq" else f"n.{q(c)}" for c in names)
        con.execute(f"CREATE OR REPLACE TEMP TABLE newj2 AS SELECT {sel} FROM newj n")
        cols = ", ".join(q(c) for c in names)
        con.execute("INSERT INTO share_origin SELECT ?, leader_id || '|' || CAST(seq AS "
                    "VARCHAR), ?, ? FROM newj2 ON CONFLICT DO NOTHING",
                    [sp.name, res.src, import_id])
        con.execute(f"INSERT INTO {tbl} ({cols}) SELECT {cols} FROM newj2")
    return res
