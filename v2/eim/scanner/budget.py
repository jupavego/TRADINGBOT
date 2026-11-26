"""Medición del presupuesto del escáner (T93) → `reports/scanner_budget.md`.

Dos barridos seguidos del universo real con el MISMO `asof` (el de la última vela guardada,
para que sea reproducible) sobre una base en memoria:

1. **En frío**: tiempo por etapa, instrumentos por segundo, ms por instrumento frente al
   presupuesto de T87 y memoria (pico de asignaciones de Python/NumPy y pico del proceso).
2. **En caliente**: mismas entradas → misma huella de puntuaciones (reproducible) y acierto de
   la caché de la cola en la lista corta.

**Proyección a 1 000 y 10 000 instrumentos**: la etapa 3 y las estadísticas se **miden** sobre
paneles sintéticos de ese tamaño (paseo aleatorio con semilla: nunca se presentan como
mercado); la lectura del almacén y los filtros, que crecen con el número de series, se
proyectan lineal desde lo medido en el universo real (por instrumento que llega a la
etapa 2). La memoria del panel es exacta (S × N × 6 columnas de 8 bytes).
"""

from __future__ import annotations

import sys
import time
import tracemalloc

from eim.scanner import screen
from eim.scanner.panel import synthetic
from eim.scanner.params import DEFAULT_PARAMS
from eim.scanner.service import ScannerService, data_stats

SIZES = (1_000, 10_000)


def peak_rss_mb() -> float | None:
    """Pico de memoria del proceso (MB): `PeakWorkingSetSize` en Windows, `ru_maxrss` fuera."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            k32 = ctypes.WinDLL("kernel32")                          # type: ignore[attr-defined]
            psapi = ctypes.WinDLL("psapi")                           # type: ignore[attr-defined]
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return round(pmc.PeakWorkingSetSize / 2**20, 1)
            return None
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / 2**20 if sys.platform == "darwin" else r / 1024, 1)
    except Exception:  # noqa: BLE001 - la memoria del proceso es informativa
        return None


def _funnel_s(s: dict) -> float:
    t = s["timings_json"]
    return sum(t[k] for k in ("catalog_s", "stage1_s", "load_s", "stage2_s", "screen_s"))


def project(real: dict, width: int, sizes=SIZES) -> list[dict]:
    """Etapa 3 y estadísticas medidas en sintético; lectura y filtros, lineales desde lo real."""
    n_real = max(1, real["n_stage1"])
    t = real["timings_json"]
    io_per = (t["catalog_s"] + t["stage1_s"] + t["load_s"]) / n_real
    out = []
    for n in sizes:
        p = synthetic(n, width, seed=n)
        t0 = time.perf_counter()
        data_stats(p, DEFAULT_PARAMS)
        stats_s = time.perf_counter() - t0
        res = screen.screen(p, ["crypto"] * n)
        total = io_per * n + stats_s + res.elapsed_ms / 1000
        out.append({"n": n, "screen_s": round(res.elapsed_ms / 1000, 4),
                    "stats_s": round(stats_s, 4), "io_s_projected": round(io_per * n, 3),
                    "total_s": round(total, 3), "ms_per_instrument": round(total * 1000 / n, 4),
                    "panel_mb": round(p.nbytes() / 2**20, 2)})
    return out


def measure(svc: ScannerService, asof: int) -> dict:
    tracemalloc.start()
    cold = svc.sweep(asof)
    peak_py = tracemalloc.get_traced_memory()[1] / 2**20
    warm = svc.sweep(asof)
    tracemalloc.stop()
    n_universe = cold["n_stage1"] if cold["n_stage1"] else 1
    funnel = _funnel_s(cold)
    qc, qw = cold["detail_json"]["queue"] or {}, warm["detail_json"]["queue"] or {}
    return {
        "asof": asof, "timeframe": cold["timeframe"], "cold": cold, "warm": warm,
        "funnel_s": round(funnel, 4), "instruments_per_s": round(n_universe / funnel, 1)
        if funnel else None,
        "ms_per_instrument": cold["ms_per_instrument"], "budget_ms": cold["budget_ms"],
        "within_budget": bool(cold["within_budget"]),
        "reproducible": cold["fingerprint"] == warm["fingerprint"],
        "cache_cold": qc.get("cache_hit_rate"), "cache_warm": qw.get("cache_hit_rate"),
        "peak_python_mb": round(peak_py, 1), "peak_process_mb": peak_rss_mb(),
        "procs": svc.queue.procs,
        "projection": project(cold, svc.p.n_bars),
    }


def render(m: dict) -> str:
    c, w = m["cold"], m["warm"]
    t = c["timings_json"]
    ex = c["detail_json"]["exclusions"]
    lines = [
        "# Presupuesto del escáner global (T93)", "",
        f"Universo: perpetuos USDⓈ-M de Binance liquidados en USDT (catálogo de T89, almacén de "
        f"T181). Marco `{m['timeframe']}`, `asof` = {m['asof']} (la última vela guardada: el "
        "barrido es reproducible). Modo ANÁLISIS: el escáner no envía órdenes.", "",
        "## Barrido completo (en frío)", "",
        "| Medida | Valor |", "|---|---:|",
        f"| Instrumentos en el catálogo (plaza) | {c['n_catalog']} |",
        f"| Pasan la etapa 1 (descubrimiento) | {c['n_stage1']} |",
        f"| Pasan la etapa 2 (datos) y se puntúan | {c['n_stage2']} |",
        f"| Lista corta a la cola (ritmo profundo) | {c['n_shortlist']} |",
        f"| Catálogo · etapa 1 · lectura · etapa 2 · etapa 3 (s) | {t['catalog_s']:.3f} · "
        f"{t['stage1_s']:.3f} · {t['load_s']:.3f} · {t['stage2_s']:.3f} · {t['screen_s']:.3f} |",
        f"| Embudo completo (etapas 1–3, s) | {m['funnel_s']:.3f} |",
        f"| Instrumentos con datos por segundo | {m['instruments_per_s']} |",
        f"| **ms por instrumento con datos** (etapa 2; presupuesto T87: {m['budget_ms']:g}) | "
        f"**{m['ms_per_instrument']:.3f}** — {'dentro' if m['within_budget'] else 'FUERA'} |",
        f"| Etapa 3 sola (ms por instrumento puntuado) | "
        f"{c['detail_json']['screen_ms_per_instrument']} |",
        f"| Preparación profunda de la lista corta ({m['procs']} proceso(s), s) | "
        f"{t['deep_s']:.3f} |",
        f"| Persistencia en `scanner.duckdb` (s) | {t['persist_s']:.3f} |",
        f"| Pico de memoria Python/NumPy (MB) | {m['peak_python_mb']} |",
        f"| Pico de memoria del proceso (MB) | {m['peak_process_mb'] or 'no medido'} |",
        f"| Panel en memoria (MB) | {c['detail_json']['panel_bytes'] / 2**20:.2f} |", "",
        "Exclusiones por motivo: " + (", ".join(f"`{k}` {v}" for k, v in ex.items()) or "ninguna")
        + ".", "",
        "## Reproducibilidad y caché (segundo barrido, mismas entradas)", "",
        f"- Huella de puntuaciones: `{c['fingerprint']}` → `{w['fingerprint']}` "
        f"({'idénticas' if m['reproducible'] else 'DISTINTAS'}).",
        f"- Acierto de caché de la cola: en frío {_pct(m['cache_cold'])}, en caliente "
        f"{_pct(m['cache_warm'])} (clave: instrumento, marco, hash de datos, versión).",
        f"- Embudo en caliente: {_funnel_s(w):.3f} s; preparación profunda "
        f"{w['timings_json']['deep_s']:.3f} s.", "",
        "## Proyección", "",
        "| Instrumentos | Etapa 3 (s, medida) | Estadísticas (s, medida) | Lectura+filtros (s, "
        "proyectada) | Total (s) | ms/instrumento | Panel (MB) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in m["projection"]:
        lines.append(f"| {r['n']:,} | {r['screen_s']} | {r['stats_s']} | {r['io_s_projected']} |"
                     f" {r['total_s']} | {r['ms_per_instrument']} | {r['panel_mb']} |")
    lines += ["", "La etapa 3 se mide en paneles sintéticos (paseo aleatorio con semilla); la "
              "lectura del almacén se proyecta lineal desde el universo real. Reproducible con "
              "`python -m eim.scanner budget` desde `v2/`.", ""]
    return "\n".join(lines)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"
