"""La memoria de un trabajo de la cola (T149): cuándo pausarlo no sirve y qué pedir la próxima vez.

El 9-nov `t143-maker` pidió 2 500 MB, llegó a 6,8 GB y la cola lo pausó 32 veces por «RAM libre
< 1 GB»: suspender no libera memoria, así que la causa de la pausa era él mismo. Cada 900 s se
reanudaba por fuerza y a los 5 s volvía a pausarse, durante 5 h 39 min. Decisión del usuario (◆,
2026-11-10): **cancelarlo y volver a encolarlo** para cuando quepa.

- **Presión propia:** RAM libre < 1 GB, el trabajo retiene ≥ 512 MB y sin él quedaría ≥ 1 GB
  libre. Se mata (libera todo al instante) y vuelve a la cola pidiendo su pico × 1,25 más el
  suelo de 1 GB, para que al volver a crecer no caiga otra vez bajo el umbral. Se mira con la RAM
  baja en cada sondeo, también con el trabajo ya pausado.
- **Bucle:** como mucho 2 pausas por memoria seguidas sin que el trabajo corra 90 s sin presión de
  memoria entre medias; la tercera también lo reencola, venga de quien venga la presión.
- Se mata a mitad de crecer, así que el pico visto puede quedarse corto: mientras cada vez pida
  más, se reencola; tras 2 reencolados sin crecer, o si lo que pediría no cabe en el equipo, queda
  fallido diciendo cuánto pedir. Tras reencolarlo espera margen como mucho 2 h, al final de la
  cola, para no tener presos a los trabajos que lleguen detrás.
- **Lo pedido frente a lo usado:** si el pico pasa de 1,5 × lo pedido (o de 1,5 × los 2 GB de
  admisión si no pidió nada), el registro lo dice y sugiere la cifra.
"""

from __future__ import annotations

import math

SELF_MIN_MB, MAX_MEM_PAUSES, MAX_REQUEUES = 512, 2, 2
MARGIN, OVER_FACTOR, ROUND_MB, FLOOR_MB = 1.25, 1.5, 256, 1024
REQUEUE_WAIT_S = 2 * 3600.0


class Requeue(Exception):  # noqa: N818 - es una decisión, no un error
    """El trabajo se mató porque pausarlo no liberaba la memoria que lo pausaba."""

    def __init__(self, why: str, job_ram_mb: float, ram_free_mb: int) -> None:
        super().__init__(why)
        self.why, self.job_ram_mb, self.ram_free_mb = why, job_ram_mb, ram_free_mb


def ask_for(peak_mb: float, asked_mb: int) -> int:
    """Lo que debería pedir la próxima vez: su pico con margen más el suelo que la cola deja
    libre (si no, al crecer volvería a quedar bajo el umbral), redondeado a 256 MB."""
    return max(asked_mb, math.ceil((peak_mb * MARGIN + FLOOR_MB) / ROUND_MB) * ROUND_MB)


def over_asked(peak_mb: float, asked_mb: int, admit_mb: int) -> int | None:
    """La cifra sugerida si el pico supera claramente lo pedido; None si se pidió lo justo."""
    if peak_mb > OVER_FACTOR * max(asked_mb, admit_mb):
        return ask_for(peak_mb, 0)
    return None


class Guard:
    """Estado de memoria de un trabajo mientras corre: pico y pausas por memoria seguidas."""

    def __init__(self, low_ram_mb: int, calm_s: float) -> None:
        self.low, self.calm_s = low_ram_mb, calm_s
        self.peak, self.streak = 0.0, 0
        self.calm_since: float | None = None

    def observe(self, job_ram_mb: float, ram_low: bool, paused: bool, now: float) -> None:
        self.peak = max(self.peak, job_ram_mb)
        if paused or ram_low:
            self.calm_since = None
            return
        self.calm_since = self.calm_since if self.calm_since is not None else now
        if now - self.calm_since >= self.calm_s:
            self.streak = 0                      # corrió sin apuro: el bucle se rompió solo

    def paused_for_memory(self) -> None:
        self.streak += 1

    def verdict(self, ram_free_mb: int, job_ram_mb: float, paused: bool) -> str | None:
        """Con la RAM como motivo: por qué pausar no sirve, o None si pausar puede ayudar. El bucle
        se corta al ir a pausarlo otra vez, no a mitad de una pausa."""
        if job_ram_mb >= SELF_MIN_MB and ram_free_mb + job_ram_mb >= self.low:
            return (f"la RAM la retiene el propio trabajo ({job_ram_mb:.0f} MB; sin él quedarían "
                    f"{ram_free_mb + job_ram_mb:.0f} MB libres)")
        if not paused and self.streak >= MAX_MEM_PAUSES:
            return f"{self.streak} pausas por memoria seguidas sin salida"
        return None
