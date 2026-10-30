"""Comprobación de arranque de un equipo (T125): ¿puedo seguir trabajando aquí con lo último?

Recorre los pasos de `docs/CONTINUIDAD.md` §2 —entorno, fuente central, código, datos, copias,
tareas, seguridad— y da un veredicto: LISTO (0), CON AVISOS (2) o NO SINCRONIZADO (1). Nunca
modifica nada salvo `git fetch` y su propio registro (`data/continuity/`). Si no llega a la
fuente central lo dice: no presenta lo local como si fuera lo último.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from eim.continuity import datastate, gitstate, offsite, tasks

OK, WARN, BLOCK = "OK", "AVISO", "BLOQUEO"
VERDICT = {OK: ("LISTO", 0), WARN: ("CON AVISOS", 2), BLOCK: ("NO SINCRONIZADO", 1)}
OWN_COPY_MAX_H = 36.0
LOCAL_COPY_MAX_H = 30.0
CLASH_H = 48.0


@dataclass
class Finding:
    level: str
    area: str
    text: str
    action: str = ""


@dataclass
class Report:
    at: str
    host: str
    machine: str
    findings: list[Finding] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def add(self, level: str, area: str, text: str, action: str = "") -> None:
        self.findings.append(Finding(level, area, text, action))

    @property
    def level(self) -> str:
        got = {f.level for f in self.findings}
        return BLOCK if BLOCK in got else WARN if WARN in got else OK

    @property
    def verdict(self) -> tuple[str, int]:
        return VERDICT[self.level]


def _environment(r: Report, v2: Path) -> None:
    """Entorno del checkout PRINCIPAL (de él corren los servicios y la interfaz), aunque la
    comprobación se lance desde un worktree."""
    try:
        v2 = gitstate.main_root(v2) / "v2"
    except gitstate.GitFailed:
        pass
    ok = sys.version_info >= (3, 11)
    r.add(OK if ok else WARN, "entorno", f"Python {platform.python_version()} ({sys.executable})",
          "" if ok else "instala Python 3.12 (`docs/MIGRACION_EQUIPO.md` §B)")
    if not (v2 / ".venv").exists() and sys.prefix == sys.base_prefix:
        r.add(WARN, "entorno", "sin entorno virtual v2/.venv",
              "powershell -ExecutionPolicy Bypass -File v2\\scripts\\preparar_equipo.ps1")
    missing = [m for m in ("fastapi", "duckdb", "scipy", "pydantic")
               if importlib.util.find_spec(m) is None]
    if missing:
        r.add(WARN, "entorno", "faltan dependencias: " + ", ".join(missing),
              "pip install -r requirements-lock.txt && pip install -e .[dev]")
    if not shutil.which("node") or not (v2 / "eim" / "web" / "node_modules").exists():
        r.add(WARN, "entorno", "interfaz sin instalar (node o node_modules)",
              "cd v2/eim/web && npm ci")


def _code(r: Report, repo: Path, fetch: bool) -> None:
    try:
        c = gitstate.state(repo, fetch=fetch)
    except gitstate.GitFailed as e:
        r.add(BLOCK, "código", f"no es un repositorio git utilizable: {e}")
        return
    r.facts["code"] = {"branch": c.branch, "head": c.head, "date": c.head_date,
                       "behind_main": c.behind_main, "ahead_main": c.ahead_main,
                       "unpublished": c.unpublished, "remote": c.remote_url}
    if fetch and not c.fetched:
        r.add(BLOCK, "central", "no se pudo consultar el repositorio central (git fetch): "
              "sincronización NO completada; lo que ves es el último estado traído",
              f"revisa red y credenciales (`gh auth status`) — {c.fetch_error[:160]}")
    r.add(OK, "código", f"{c.branch} @ {c.head} ({c.head_date[:16]}) · {c.remote_url}")
    if c.behind_main:
        clean = not any(w.dirty for w in c.worktrees if Path(w.path) == Path(c.root))
        r.add(WARN, "código", f"{c.behind_main} commit(s) de origin/main que este checkout no "
              "tiene", "git pull --ff-only" if c.branch == "main" and clean else
              "guarda tu trabajo y trae main (`git merge origin/main`)")
    for u in c.unpublished:
        r.add(WARN, "código", f"solo en este equipo: {u}",
              "commit + push a una rama (o `python -m eim.continuity publish`, que lo guarda "
              "como parche en la copia externa)")


def _remote(r: Report, t: offsite.Releases, ds: datastate.DataState, host: str) -> None:
    try:
        copies = offsite.remote_copies(t)
    except offsite.OffsiteError as e:
        r.add(WARN, "copias", f"no se pudo consultar la copia externa ({t.repo}): {e}",
              "gh auth login  (y acceso al repo privado de datos)")
        return
    latest: dict[str, offsite.RemoteCopy] = {}
    for c in copies:
        if c.complete:
            latest[c.machine] = c
    r.facts["remote"] = {m: {"backup": c.backup, "host": c.meta.get("host"),
                             "published_at": c.meta.get("published_at"),
                             "rows": {db: sum(t.values()) for db, t in c.rows.items()}}
                         for m, c in latest.items()}
    for m, c in sorted(latest.items()):
        mark = " (este equipo)" if m == ds.machine else ""
        r.add(OK, "copias", f"copia externa de {m}{mark}: {c.backup} desde "
              f"{c.meta.get('host', '?')}, publicada {c.meta.get('published_at', '?')[:16]}")
    mine = latest.get(ds.machine)
    if mine is None:
        if not ds.empty:
            r.add(WARN, "copias", "este equipo no tiene copia externa",
                  "python -m eim.continuity publish")
        return
    age_h = _age_h(mine.meta.get("published_at"))
    if mine.meta.get("host") not in (None, host) and age_h is not None and age_h < CLASH_H:
        r.add(BLOCK, "datos", f"la identidad {ds.machine} publicó hace {age_h:.0f} h desde OTRO "
              f"equipo ({mine.meta.get('host')}): dos equipos con la misma identidad chocan",
              "define `EIM_MACHINE` con un alias propio en uno de los dos "
              "(`docs/CONTINUIDAD.md` §4)")
    if age_h is not None and age_h > OWN_COPY_MAX_H and not ds.empty:
        r.add(WARN, "copias", f"la copia externa de este equipo tiene {age_h:.0f} h",
              "python -m eim.continuity publish")
    local = {db: d["rows"] for db, d in ds.dbs.items() if d.get("rows") is not None}
    if stale := datastate.stale_dbs(local, mine.rows):
        r.add(BLOCK, "datos", "estos datos son MÁS VIEJOS que la copia ya publicada de este "
              "equipo: " + "; ".join(stale),
              f"python -m eim.continuity offsite pull --machine {ds.machine} y "
              "`python -m eim.data.backup restore <carpeta>` con los servicios detenidos")


def _age_h(iso: str | None) -> float | None:
    try:
        return (time.time() - datetime.fromisoformat(iso).timestamp()) / 3600.0
    except (TypeError, ValueError):
        return None


def _data(r: Report, ds: datastate.DataState) -> None:
    r.facts["data"] = asdict(ds)
    if ds.empty:
        r.add(BLOCK, "datos", f"{ds.data_dir} no tiene historial (sin bases): la API crearía "
              "bases VACÍAS", "no arranques nada; recupera: `python -m eim.continuity offsite "
              "pull` + `backup restore`, o importa la experiencia (`docs/CONTINUIDAD.md` §3)")
        return
    for db, d in ds.dbs.items():
        rows = (f"{sum(d['rows'].values()):,} filas" if d["rows"] is not None
                else "en uso por un servicio" if d["in_use"] else "sin leer")
        r.add(OK, "datos", f"{db}: {d['bytes'] / 1e6:,.0f} MB, {rows}")
    if ds.running():
        r.add(OK, "procesos", "servicios con latido reciente: " + ", ".join(ds.running()))
    if not ds.last_backup:
        r.add(WARN, "copias", "no hay copia local completa", "python -m eim.data.backup create")
    elif ds.last_backup_age_h is not None and ds.last_backup_age_h > LOCAL_COPY_MAX_H:
        r.add(WARN, "copias", f"última copia local completa: {ds.last_backup} "
              f"({ds.last_backup_age_h:.0f} h)", "python -m eim.data.backup create")
    else:
        r.add(OK, "copias", f"última copia local completa: {ds.last_backup} "
              f"({ds.last_backup_age_h} h)")
    if not ds.share_configured:
        r.add(OK, "datos", "experiencia compartida sin configurar en esta carpeta (T117: se "
              "activa tras revisar los simulacros)")


def _tasks(r: Report, plan: Path) -> None:
    t = tasks.read(plan)
    doing = ", ".join(i for i, _ in t.by_state["en curso"])
    r.facts["tasks"] = {k: [i for i, _ in v] for k, v in t.by_state.items()}
    r.add(OK, "tareas", f"{t.count('hecha')} hechas · {t.count('en curso')} en curso ({doing}) "
          f"· {t.count('pendiente')} pendientes · {t.backlog_lines} entradas en BACKLOG")
    if t.last_session:
        r.add(OK, "tareas", f"última sesión: {t.last_session}"
              + (f" → siguiente paso: {t.next_step}" if t.next_step else ""))


def _safety(r: Report, env: dict) -> None:
    mode = env.get("EIM_EXECUTION", "off")
    keys = sorted(k for k in env if k.startswith("EIM_") and k.endswith(("_KEY", "_SECRET")))
    r.add(OK, "seguridad", f"ejecución por defecto: {mode}; modo REAL prohibido por la "
          "configuración de riesgo (sin dinero real)")
    if keys:
        r.add(WARN, "seguridad", "claves en este equipo: " + ", ".join(keys),
              "solo testnet sin retiro, y en UN solo equipo a la vez")


def run(v2: Path, data_dir: Path, backup_dir: Path, *, network: bool = True,
        env: dict | None = None, transport: offsite.Releases | None = None) -> Report:
    env = dict(os.environ if env is None else env)
    host = platform.node()
    ds = datastate.state(data_dir, backup_dir)
    r = Report(datetime.now(UTC).isoformat(timespec="seconds"), host, ds.machine or "(sin id)")
    _environment(r, v2)
    _code(r, v2, fetch=network)
    _data(r, ds)
    if network:
        _remote(r, transport or offsite.Releases(offsite.repo_from_env(env), timeout=120), ds,
                host)
    else:
        r.add(WARN, "central", "comprobación sin red: no se consultó la fuente central")
    _tasks(r, v2.parent / "PLAN")
    _safety(r, env)
    return r


def render(r: Report) -> str:
    name, _ = r.verdict
    out = [f"EIM · comprobación de continuidad · {r.at} · equipo {r.host} · identidad {r.machine}"]
    for area in dict.fromkeys(f.area for f in r.findings):
        out.append(f"\n[{area}]")
        for f in (f for f in r.findings if f.area == area):
            tail = f"\n          → {f.action}" if f.action else ""
            out.append(f"  {f.level:<7} {f.text}{tail}")
    out.append(f"\nVEREDICTO: {name}")
    if r.level == BLOCK:
        out.append("No continúes hasta resolver los BLOQUEO: los datos o el código de este equipo "
                   "no están al día o no se pudo comprobar.")
    return "\n".join(out)


def record(r: Report, data_dir: Path) -> Path:
    d = Path(data_dir) / "continuity"
    d.mkdir(parents=True, exist_ok=True)
    row = {"at": r.at, "host": r.host, "machine": r.machine, "verdict": r.verdict[0],
           "findings": [asdict(f) for f in r.findings], "facts": r.facts}
    text = json.dumps(row, ensure_ascii=False, default=str)
    (d / "last_check.json").write_text(text, encoding="utf-8")
    with (d / "checks.jsonl").open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    return d / "last_check.json"

