"""Un vigilante del conjunto, fuera del conjunto (T148, entregable 1).

El 2026-11-09 los cinco servicios del EIM estuvieron parados **5 h 26 min** y nadie los levantó.
No por falta de vigilantes, sino porque cada uno solo relanza a sus **hijos**: `eim.operation run`
relanza la API (T140), `hft_supervise` la captura, `eim.leaders supervise` la suya. Si mueren los
vigilantes no queda nadie, y las tareas programadas `EIM - servicio continuo` solo saltan al
encender y al iniciar sesión, así que con Windows ya encendido y la sesión abierta no vuelven a
saltar. El apagón duró lo que tardó una persona en mirar
(`PLAN/notas/T148_apagon_2026-11-09.md`).

Esto es lo que faltaba: algo que **no sea hijo de lo que vigila**. Una tarea programada con
disparador repetido lo llama cada `EVERY_MIN` minutos; él mira los latidos de los cinco y, si
alguno lleva `DOWN_S` sin dar señales, corre `servicio_continuo.ps1`, que ya es idempotente.
Decidido por el usuario (2026-11-09): **comprobar cada 5 min y levantar tras 10 min sin latido**
—el doble del ciclo más lento, así que no pisa un reinicio en curso— y **solo los cinco servicios
de datos**, sin `-ConWeb`: son los que pierden información.

**No entrar en bucle** (como el vigilante del puerto de T140): tope de `MAX_TRIES` intentos con
espera creciente (`BACKOFF_S`). Si el arranque falla cuatro veces se rinde, avisa y no reintenta
hasta `GIVE_UP_S` después: un arranque roto no se arregla repitiéndolo cada 5 min, y entretanto la
persona es el único recurso que queda. Cada intento queda registrado con **qué faltaba y cuánto
llevaba caído**, y la recuperación también (entregable 5). El estado entre pasadas vive en
`data/operation/fleet_watch.json`, porque cada pasada es un proceso nuevo que muere al acabar.

Instalación y comprobación: `v2/docs/RUNBOOK.md` §18.

    python -m eim.operation.fleet_watch status        # qué ve, sin tocar nada
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from eim.operation.alerts import Alert
from eim.operation.fleet_alert import alert_for, announce
from eim.operation.notify import JsonLog, WindowsToast
from eim.operation.usage_summary import load_day

COMPONENT = "operation.fleet_watch"
EVERY_MIN = 5                    # cada cuánto lo llama la tarea programada (decisión del usuario)
DOWN_S = 600.0                   # sin latido durante esto = caído (decisión del usuario)
MAX_TRIES = 4
BACKOFF_S = (0.0, 300.0, 900.0, 1800.0)   # espera antes del intento 1.º, 2.º, 3.º y 4.º
GIVE_UP_S = 21_600.0             # tras rendirse, no se reintenta hasta 6 h después
USAGE = "registro de consumo"
# Los cuatro que publican latido en un archivo. El quinto (el registro de consumo) no tiene
# ninguno: se deduce de sus propias muestras, que es lo que de verdad produce, y así esta pasada
# no obliga a reiniciarlo para que estrene un latido nuevo.
BEATS = {"API": "operation/heartbeat.json", "bróker simulado": "paper/heartbeat.json",
         "líderes": "leaders/heartbeat.json", "captura HFT": "micro_hft/heartbeat.json"}


# --------------------------------------------------------------------------------- qué está vivo

def _beat_ms(path: Path) -> int | None:
    """Milisegundos del último latido. Se miran las dos claves que el EIM usa: la operación, los
    líderes y la captura escriben `last_heartbeat`, y el bróker simulado `last_tick`
    (`eim.continuity.datastate` lo lee igual). Se lee aquí en vez de importar ese módulo para no
    arrastrar DuckDB y pydantic en una pasada que corre cada 5 min."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for k in ("last_heartbeat", "last_tick"):
        v = d.get(k) if isinstance(d, dict) else None
        if isinstance(v, (int, float)) and v > 1e12:
            return int(v)
    return None


def _usage_beat_ms(data_dir: Path, now_s: float) -> int | None:
    """Última muestra del registro de consumo (hoy o, en el cambio de día, ayer)."""
    best = None
    for off in (0, 86_400):
        day = time.strftime("%Y-%m-%d", time.gmtime(now_s - off))
        if recs := load_day(data_dir, day):
            best = max(int(r["t"]) for r in recs if isinstance(r.get("t"), (int, float)))
            break
    return best


def ages(data_dir: Path, now_s: float | None = None) -> dict[str, float | None]:
    """Segundos desde la última señal de vida de cada servicio. None = ninguna señal.

    None no es «caído desde siempre»: es «nunca dio señales», que en un equipo recién instalado
    también se levanta, y en uno con datos significa que el archivo no se puede leer."""
    now = time.time() if now_s is None else now_s
    out: dict[str, float | None] = {}
    for name, rel in BEATS.items():
        ms = _beat_ms(Path(data_dir) / rel)
        out[name] = None if ms is None else round(now - ms / 1000.0, 1)
    ms = _usage_beat_ms(Path(data_dir), now)
    out[USAGE] = None if ms is None else round(now - ms / 1000.0, 1)
    return out


def missing(seen: Mapping[str, float | None], down_s: float = DOWN_S) -> list[str]:
    """Los que llevan `down_s` sin señal, en el orden de siempre."""
    return [k for k, age in seen.items() if age is None or age >= down_s]


# ---------------------------------------------------------------------------------- qué hacer

@dataclass
class State:
    """Lo que esta pasada necesita saber de las anteriores."""

    tries: int = 0
    down_since_ms: int | None = None
    last_try_ms: int | None = None
    gave_up_ms: int | None = None
    last_missing: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> State:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        f = {k: d.get(k) for k in ("tries", "down_since_ms", "last_try_ms", "gave_up_ms")}
        return cls(int(f["tries"] or 0), f["down_since_ms"], f["last_try_ms"], f["gave_up_ms"],
                   list(d.get("last_missing") or []))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tries": self.tries, "down_since_ms": self.down_since_ms,
                                   "last_try_ms": self.last_try_ms, "gave_up_ms": self.gave_up_ms,
                                   "last_missing": self.last_missing}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)


@dataclass(frozen=True)
class Decision:
    """Qué toca en esta pasada y por qué, para poder registrarlo sin volver a razonarlo."""

    action: str                  # "ok" | "recuperado" | "levantar" | "esperar" | "rendirse"
    missing: tuple[str, ...] = ()
    down_s: float = 0.0          # cuánto lleva caído el conjunto, no cada servicio
    wait_s: float = 0.0          # lo que falta para el siguiente intento ("esperar")
    tries: int = 0

    @property
    def lift(self) -> bool:
        return self.action == "levantar"


def decide(seen: Mapping[str, float | None], state: State, now_ms: int,
           down_s: float = DOWN_S, max_tries: int = MAX_TRIES) -> Decision:
    """Regla pura: lo que ven los latidos y lo que pasó antes → qué hacer ahora.

    - nada caído: «ok», o «recuperado» si se venía de un apagón (hay que avisar y olvidarlo);
    - algo caído: «levantar» si ya toca, «esperar» si la espera creciente aún corre, «rendirse»
      si se agotaron los intentos (y hasta `GIVE_UP_S` después no se vuelve a probar).
    """
    down = missing(seen, down_s)
    if not down:
        if state.tries or state.down_since_ms:
            return Decision("recuperado", tuple(state.last_missing), tries=state.tries,
                            down_s=round((now_ms - (state.down_since_ms or now_ms)) / 1000, 1))
        return Decision("ok")
    # Caído desde el latido más viejo de los que faltan, no desde que esta pasada lo vio: el
    # aviso dice cuánto llevaba caído. Sin ningún latido (None) no se sabe: se cuenta desde ya.
    oldest = max((seen[k] for k in down if seen[k] is not None), default=0.0)
    since = state.down_since_ms or now_ms - int(oldest * 1000)
    elapsed = round((now_ms - since) / 1000, 1)
    tries = state.tries
    if state.gave_up_ms is not None:
        if now_ms - state.gave_up_ms < GIVE_UP_S * 1000:
            return Decision("rendirse", tuple(down), elapsed, tries=tries,
                            wait_s=round(GIVE_UP_S - (now_ms - state.gave_up_ms) / 1000, 1))
        tries = 0                 # cumplida la penitencia, se vuelve a empezar desde el intento 1
    if tries >= max_tries:
        return Decision("rendirse", tuple(down), elapsed, tries=tries)
    wait = BACKOFF_S[min(tries, len(BACKOFF_S) - 1)] * 1000
    if tries and state.last_try_ms is not None and now_ms - state.last_try_ms < wait:
        return Decision("esperar", tuple(down), elapsed, tries=tries,
                        wait_s=round((wait - (now_ms - state.last_try_ms)) / 1000, 1))
    return Decision("levantar", tuple(down), elapsed, tries=tries + 1)


# ------------------------------------------------------------------------------------- levantar

def script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "servicio_continuo.ps1"


def launch(data_dir: Path, timeout_s: float = 600.0) -> tuple[int, str]:
    """Corre `servicio_continuo.ps1` SIN `-ConWeb` (decisión del usuario: solo los de datos).

    Devuelve (código de salida, últimas líneas). No lanza: un arranque que falla es un dato que
    hay que registrar, no una excepción que tumbe la pasada."""
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-WindowStyle", "Hidden", "-File", str(script_path()), "-DataDir", str(data_dir)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",  # noqa: S603
                           errors="replace", timeout=timeout_s, check=False)
    except FileNotFoundError:
        return 127, "no se encontró powershell.exe"
    except subprocess.TimeoutExpired:
        return 124, f"el arranque no terminó en {timeout_s:.0f} s"
    tail = "\n".join([*(p.stdout or "").splitlines(), *(p.stderr or "").splitlines()][-12:])
    return p.returncode, tail[:1500]


# ---------------------------------------------------------------------------------- una pasada

def check(data_dir: Path, now_s: float | None = None, down_s: float = DOWN_S,
          dry_run: bool = False, launcher: Callable[[Path], tuple[int, str]] | None = None,
          notify: bool = True) -> dict:
    """Una pasada: mirar, decidir, levantar si toca y dejarlo todo registrado."""
    now = time.time() if now_s is None else now_s
    now_ms = int(now * 1000)
    data_dir = Path(data_dir)
    state_path = data_dir / "operation" / "fleet_watch.json"
    st = State.load(state_path)
    seen = ages(data_dir, now)
    d = decide(seen, st, now_ms, down_s)
    rc, tail = None, ""
    if d.lift and not dry_run:
        rc, tail = (launcher or launch)(data_dir)
    out = {"action": "simulado" if (d.lift and dry_run) else d.action, "missing": list(d.missing),
           "down_s": d.down_s, "tries": d.tries, "wait_s": d.wait_s,
           "ages_s": dict(seen), "rc": rc, **({"detail": tail} if tail else {})}
    if dry_run:
        return out
    if d.action == "levantar":
        st.tries, st.last_try_ms = d.tries, now_ms
        st.down_since_ms = st.down_since_ms or now_ms - int(d.down_s * 1000)
        st.last_missing = list(d.missing)
        if d.tries == 1:
            st.gave_up_ms = None
        if d.tries >= MAX_TRIES and rc not in (0, None):
            st.gave_up_ms = now_ms
    elif d.action == "rendirse" and not d.wait_s:
        st.gave_up_ms = now_ms
    elif d.action == "recuperado":
        st = State()
    elif d.action == "ok":
        st.down_since_ms = st.down_since_ms if d.missing else None
    st.save(state_path)
    log = JsonLog(data_dir / "operation" / "logs", clock=lambda: now_ms)
    if d.action != "ok":
        log.write(f"conjunto_{d.action}", "warn" if d.action != "recuperado" else "info",
                  component=COMPONENT, **{k: v for k, v in out.items() if k != "action"})
    a = alert_for(d.action, d.missing, d.down_s, d.tries, MAX_TRIES, rc, GIVE_UP_S,
                  waiting=bool(d.wait_s))
    if a is not None:
        announce(Alert(now_ms, a.kind, a.level, a.title, a.detail, a.key, a.resolved),
                 log.alert_sink, WindowsToast() if notify else None,
                 lambda err: log.write("conjunto_aviso_fallido", "warn", component=COMPONENT,
                                       error=err))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.fleet_watch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("check", "una pasada: levanta el conjunto si falta algún latido"),
                           ("status", "qué latidos se ven, sin tocar nada")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--data-dir", default="data")
        s.add_argument("--down-s", type=float, default=DOWN_S)
        if name == "check":
            s.add_argument("--dry-run", action="store_true", help="decide pero no lanza nada")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        seen = ages(Path(a.data_dir))
        out = {"ages_s": seen, "missing": missing(seen, a.down_s),
               "state": vars(State.load(Path(a.data_dir) / "operation" / "fleet_watch.json"))}
    else:
        out = check(Path(a.data_dir), down_s=a.down_s, dry_run=a.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    # Para `Get-ScheduledTaskInfo`: 0 = nada que arreglar o arreglado; 1 = sigue caído y hay que
    # mirarlo. «esperar» es normal (la espera creciente aún corre), no un fallo de la tarea.
    bad = out.get("action") == "rendirse" or (out.get("rc") not in (0, None))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
