"""Plan de muestreo del examen físico (T169), congelado antes de correr. Puro salvo `freeze`.

Declarado en `PLAN/T169.md` («Plan de muestreo y costo», 2026-11-16): 4 h entera desde 2023-04-01;
1 h en bloques de 28 días, uno de cada tres (k ≡ 0 mod 3); 15 m en los 14 primeros días de esos
mismos bloques. Solo corren los agentes con prospectos **con historia**: `bots`, `derivatives`,
`liquidations` y `microstructure` piden datos que el banco no guarda y se examinan hacia adelante.

La ventana queda en `plan.json` con el SHA-256 de cada parquet del banco: al relanzar se comprueba
que ni el banco ni los prospectos cambiaron, para que una corrida reanudada mida lo mismo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from eim.data.timeframes import FOCUS, tf_ms
from eim.nursery.prospect import Prospect, native_paths

DAY_MS = 86_400_000
EPOCH_MS = 1_680_307_200_000      # 2023-04-01T00:00Z: ventanas de 500 velas (y 4 h vecinas) llenas
BLOCK_DAYS, EVERY, PHASE, M15_DAYS = 28, 3, 0, 14
TFS = ("4h", "15m", "1h")         # orden de cálculo: de lo barato a lo caro
WHY_NO_HISTORY = {
    "bots": "pide las señales del servicio de bots, que no se guardan",
    "derivatives": "el agente exige interés abierto y el banco solo tiene funding",
    "liquidations": "pide liquidaciones en vivo, que el banco no tiene",
    "microstructure": "pide la captura HFT, que el banco no tiene",
}
HISTORYLESS = frozenset(WHY_NO_HISTORY)


@dataclass(frozen=True)
class Stretch:
    """Un tramo seguido de un marco: contextos con cierre en (start, end], de vela en vela."""

    tf: str
    block: int                 # k del bloque de 28 días; −1 = la historia seguida (4 h)
    start: int
    end: int

    def asofs(self) -> list[int]:
        bar = tf_ms(self.tf)
        return list(range(self.start + bar, self.end + 1, bar))

    @property
    def days(self) -> float:
        return (self.end - self.start) / DAY_MS


def block_start(k: int) -> int:
    return EPOCH_MS + k * BLOCK_DAYS * DAY_MS


def block_of(t: int) -> int:
    """Bloque de 28 días al que pertenece un instante."""
    return (int(t) - EPOCH_MS) // (BLOCK_DAYS * DAY_MS)


def sampled_blocks(last_asof: int) -> list[int]:
    """Bloques completos hasta `last_asof`, uno de cada `EVERY` (sistemático, sin elegir)."""
    n = (last_asof - EPOCH_MS) // (BLOCK_DAYS * DAY_MS)
    return [k for k in range(int(n)) if k % EVERY == PHASE]


def stretches(last: dict[str, int]) -> dict[str, list[Stretch]]:
    """Tramos por marco a partir del último cierre del banco en cada marco."""
    ks = sampled_blocks(min(last["1h"], last["15m"]))
    blk = BLOCK_DAYS * DAY_MS
    return {
        "4h": [Stretch("4h", -1, EPOCH_MS, int(last["4h"]))],
        "15m": [Stretch("15m", k, block_start(k), block_start(k) + M15_DAYS * DAY_MS)
                for k in ks],
        "1h": [Stretch("1h", k, block_start(k), block_start(k) + blk) for k in ks],
    }


def with_history(prospects: Sequence[Prospect]) -> tuple[Prospect, ...]:
    return tuple(p for p in prospects if p.agent_id not in HISTORYLESS)


def agents_by_tf(prospects: Sequence[Prospect]) -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}
    for p in with_history(prospects):
        out.setdefault(p.timeframe, set()).add(p.agent_id)
    return {tf: sorted(v) for tf, v in sorted(out.items())}


def bank_files(root: Path) -> dict[str, str]:
    """SHA-256 de cada parquet del banco (ruta relativa → huella)."""
    out = {}
    for f in sorted(root.rglob("*.parquet")):
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        out[f.relative_to(root).as_posix()] = h.hexdigest()
    return out


def build(prospects: Sequence[Prospect], last: dict[str, int], bank: Path,
          files: dict[str, str]) -> dict:
    """El plan entero, listo para congelar."""
    hist = with_history(prospects)
    return {
        "version": 1, "symbol": FOCUS[0], "bank": str(bank), "bank_files": files,
        "last_asof": {tf: int(v) for tf, v in sorted(last.items())},
        "rule": {"epoch_ms": EPOCH_MS, "block_days": BLOCK_DAYS, "every": EVERY,
                 "phase": PHASE, "m15_days": M15_DAYS},
        "stretches": {tf: [[s.block, s.start, s.end] for s in ss]
                      for tf, ss in stretches(last).items()},
        "agents": agents_by_tf(prospects),
        "native": {a: list(v) for a, v in native_paths(hist).items()},
        "prospects": {p.id: p.fingerprint for p in hist},
        "without_history": {p.id: WHY_NO_HISTORY[p.agent_id] for p in prospects
                            if p.agent_id in HISTORYLESS},
    }


def stretches_of(plan: dict) -> dict[str, list[Stretch]]:
    return {tf: [Stretch(tf, int(b), int(s), int(e)) for b, s, e in rows]
            for tf, rows in plan["stretches"].items()}


def freeze(path: Path, plan: dict) -> dict:
    """Escribe el plan si no existe; si existe, exige que sea el mismo (ventana congelada)."""
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old != plan:
            diff = sorted(k for k in set(old) | set(plan) if old.get(k) != plan.get(k))
            raise ValueError(f"{path} ya congela otra ventana (cambia: {diff}); "
                             "usa otra carpeta de trabajo")
        return old
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return plan
