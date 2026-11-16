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

**Lo que T173 añadió, porque el 2026-11-10 los cuatro intentos no sirvieron de nada:** antes de
relanzar se mira si hay una razón por la que relanzar no puede funcionar (`fleet_cause.py`) —un
corte de red en marcha, o un servicio que vive dentro de otro que está vivo—; en esos casos no se
gasta intento, se avisa una vez y se sigue contando la caída. Y un intento se cuenta por su
**efecto**: si en la pasada siguiente el latido no avanzó, queda «sin efecto», porque un guion que
devuelve 0 sin haber lanzado nada no es un arranque bueno.

Instalación y comprobación: `v2/docs/RUNBOOK.md` §18.

    python -m eim.operation.fleet_watch status        # qué ve, sin tocar nada
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from eim.operation import fleet_cause
from eim.operation.alerts import Alert
from eim.operation.fleet_alert import alert_for, announce, stuck_alert
from eim.operation.fleet_state import Decision, State
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


def beats_ms(data_dir: Path, now_s: float | None = None) -> dict[str, int | None]:
    """El último latido de cada servicio, en milisegundos. None = ninguna señal.

    El valor absoluto, no la edad: T173 compara el latido de antes de un intento con el de la
    pasada siguiente para saber si el intento sirvió de algo."""
    now = time.time() if now_s is None else now_s
    out: dict[str, int | None] = {n: _beat_ms(Path(data_dir) / rel) for n, rel in BEATS.items()}
    out[USAGE] = _usage_beat_ms(Path(data_dir), now)
    return out


def ages(data_dir: Path, now_s: float | None = None) -> dict[str, float | None]:
    """Segundos desde la última señal de vida de cada servicio. None = ninguna señal.

    None no es «caído desde siempre»: es «nunca dio señales», que en un equipo recién instalado
    también se levanta, y en uno con datos significa que el archivo no se puede leer."""
    now = time.time() if now_s is None else now_s
    return {n: None if ms is None else round(now - ms / 1000.0, 1)
            for n, ms in beats_ms(Path(data_dir), now).items()}


def missing(seen: Mapping[str, float | None], down_s: float = DOWN_S) -> list[str]:
    """Los que llevan `down_s` sin señal, en el orden de siempre."""
    return [k for k, age in seen.items() if age is None or age >= down_s]


def _no_effect(state: State, beats: Mapping[str, int | None] | None) -> bool:
    """¿El último intento movió algún latido de los que faltaban? (T173 E2)

    `rc=0` del guion no prueba nada: el 2026-11-10 devolvió 0 cuatro veces sin tocar nada. Lo que
    lo prueba es el latido de la pasada siguiente. Sin intento previo o sin latidos que comparar,
    no se afirma nada."""
    if beats is None or state.last_try_ms is None or not state.last_try_beats:
        return False
    antes = {k: v for k, v in state.last_try_beats.items() if k in beats}
    return bool(antes) and all(beats[k] == v for k, v in antes.items())


def decide(seen: Mapping[str, float | None], state: State, now_ms: int,
           down_s: float = DOWN_S, max_tries: int = MAX_TRIES, blocked: dict | None = None,
           beats: Mapping[str, int | None] | None = None) -> Decision:
    """Regla pura: lo que ven los latidos y lo que pasó antes → qué hacer ahora.

    - nada caído: «ok», o «recuperado» si se venía de un apagón (hay que avisar y olvidarlo);
    - algo caído con una causa por la que relanzar no puede servir (T173): «sin_red» mientras dura
      un corte de red, «dentro_de_otro» si lo que falta vive dentro de otro que sí late. Ninguna
      de las dos gasta intento, porque el 2026-11-10 los cuatro se gastaron en balde;
    - algo caído y nuestro remedio sirve: «levantar» si ya toca, «esperar» si la espera creciente
      aún corre, «rendirse» si se agotaron los intentos (y hasta `GIVE_UP_S` después no se
      vuelve a probar).
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
    nada = _no_effect(state, beats)
    inside = tuple(fleet_cause.not_liftable(down, dict(seen), down_s))
    if blocked is not None:
        return Decision("sin_red", tuple(down), elapsed, tries=state.tries, blocked=blocked,
                        inside=inside, no_effect=nada)
    if state.said == "sin_red":   # volvió la red: una pasada de gracia para que lata solo (E1)
        return Decision("esperar", tuple(down), elapsed, tries=state.tries, inside=inside,
                        wait_s=float(EVERY_MIN * 60), no_effect=nada)
    if inside and len(inside) == len(down):
        return Decision("dentro_de_otro", tuple(down), elapsed, tries=state.tries, inside=inside,
                        no_effect=nada)
    tries = state.tries
    if state.gave_up_ms is not None:
        if now_ms - state.gave_up_ms < GIVE_UP_S * 1000:
            return Decision("rendirse", tuple(down), elapsed, tries=tries, inside=inside,
                            no_effect=nada,
                            wait_s=round(GIVE_UP_S - (now_ms - state.gave_up_ms) / 1000, 1))
        tries = 0                 # cumplida la penitencia, se vuelve a empezar desde el intento 1
    if tries >= max_tries:
        return Decision("rendirse", tuple(down), elapsed, tries=tries, inside=inside,
                        no_effect=nada)
    wait = BACKOFF_S[min(tries, len(BACKOFF_S) - 1)] * 1000
    if tries and state.last_try_ms is not None and now_ms - state.last_try_ms < wait:
        return Decision("esperar", tuple(down), elapsed, tries=tries, inside=inside,
                        no_effect=nada,
                        wait_s=round((wait - (now_ms - state.last_try_ms)) / 1000, 1))
    return Decision("levantar", tuple(down), elapsed, tries=tries + 1, inside=inside,
                    no_effect=nada)


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
          notify: bool = True, ops: list[dict] | None = None) -> dict:
    """Una pasada: mirar, decidir, levantar si toca y dejarlo todo registrado.

    `ops` permite pasar los eventos de operación ya leídos (las pruebas lo usan); si no, se leen
    de `data/operation/logs`."""
    now = time.time() if now_s is None else now_s
    now_ms = int(now * 1000)
    data_dir = Path(data_dir)
    state_path = data_dir / "operation" / "fleet_watch.json"
    st = State.load(state_path)
    beats = beats_ms(data_dir, now)
    seen = {n: None if ms is None else round(now - ms / 1000.0, 1) for n, ms in beats.items()}
    rows = fleet_cause.recent_ops(data_dir, now) if ops is None else ops
    # Una alerta de desconexión abierta solo cuenta si quien la cerraría (el ciclo, en la API)
    # sigue vivo: si la API murió con ella abierta, nadie la va a cerrar y bloquearía para siempre.
    api_up = (seen.get("API") if seen.get("API") is not None else down_s) < down_s
    blocked = (fleet_cause.network_cause(rows, now_ms, trust_open_alert=api_up)
               if missing(seen, down_s) else None)
    d = decide(seen, st, now_ms, down_s, blocked=blocked, beats=beats)
    rc, tail = None, ""
    if d.lift and not dry_run:
        rc, tail = (launcher or launch)(data_dir)
    stuck = fleet_cause.not_producing(data_dir, now)
    out = {"action": "simulado" if (d.lift and dry_run) else d.action, "missing": list(d.missing),
           "down_s": d.down_s, "tries": d.tries, "wait_s": d.wait_s,
           "ages_s": dict(seen), "rc": rc,
           **({"sin_efecto": True} if d.no_effect else {}),
           **({"red": d.blocked} if d.blocked else {}),
           **({"dentro_de_otro": list(d.inside)} if d.inside else {}),
           **({"late_sin_producir": stuck} if stuck else {}),
           **({"detail": tail} if tail else {})}
    if dry_run:
        return out
    if d.action == "levantar":
        st.tries, st.last_try_ms = d.tries, now_ms
        st.down_since_ms = st.down_since_ms or now_ms - int(d.down_s * 1000)
        st.last_missing = list(d.missing)
        # T173: el latido de los que faltan, para juzgar este intento en la pasada siguiente.
        st.last_try_beats = {k: beats.get(k) for k in d.missing}
        if d.tries == 1:
            st.gave_up_ms = None
        if d.tries >= MAX_TRIES and rc not in (0, None):
            st.gave_up_ms = now_ms
    elif d.action == "rendirse" and not d.wait_s:
        st.gave_up_ms = now_ms
    elif d.action == "recuperado":
        st = State()
    elif d.action in ("ok", "sin_red", "dentro_de_otro"):
        # Ni intento ni penitencia: solo se conserva desde cuándo está caído, para decirlo bien.
        st.down_since_ms = None if not d.missing else (
            st.down_since_ms or now_ms - int(d.down_s * 1000))
        st.last_missing = list(d.missing)
    # Un estado de espera que no cambia no se vuelve a contar: el 2026-11-10 «rendirse» quedó 31
    # veces en el registro y avisó una sola, que es lo que hay que hacer con los dos.
    repetido = d.holding and st.said == d.action
    st.said = d.action if d.holding else ""
    nuevo_atasco = bool(stuck) and str(stuck.get("hour") or "") != st.stuck_hour
    st.stuck_hour = str((stuck or {}).get("hour") or "")
    st.save(state_path)
    log = JsonLog(data_dir / "operation" / "logs", clock=lambda: now_ms)
    if d.action != "ok" and not repetido:
        log.write(f"conjunto_{d.action}", "warn" if d.action != "recuperado" else "info",
                  component=COMPONENT, **{k: v for k, v in out.items() if k != "action"})
    if nuevo_atasco:
        log.write("conjunto_late_sin_producir", "warn", component=COMPONENT, **stuck)
    a = alert_for(d.action, d.missing, d.down_s, d.tries, MAX_TRIES, rc, GIVE_UP_S,
                  waiting=bool(d.wait_s), blocked=d.blocked, inside=d.inside,
                  no_effect=d.no_effect) if not repetido else None
    for x in (a, stuck_alert(stuck) if nuevo_atasco else None):
        if x is not None:
            announce(Alert(now_ms, x.kind, x.level, x.title, x.detail, x.key, x.resolved),
                     log.alert_sink, WindowsToast() if notify else None,
                     lambda err: log.write("conjunto_aviso_fallido", "warn",
                                           component=COMPONENT, error=err))
    return out


def main(argv: list[str] | None = None) -> int:
    """La línea de órdenes vive en `fleet_cli.py`; esta puerta no cambia (T173)."""
    from eim.operation.fleet_cli import main as cli

    return cli(argv)


if __name__ == "__main__":
    sys.exit(main())
