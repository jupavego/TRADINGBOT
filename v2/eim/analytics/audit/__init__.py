"""Auditoría periódica de rentabilidad y calibración (T159, fase 25).

Convierte el diagnóstico manual de la fase 24 en un comando repetible y barato de leer:

    python -m eim.analytics.audit [--api http://127.0.0.1:8000] [--data-dir data]
                                  [--out reports/audit] [--sin-red] [--ledger libro.csv]

Escribe `reports/audit/audit_AAAA-MM-DD.{json,md}` y saca por consola un resumen de ≈ 25 líneas
con las diferencias frente a la auditoría anterior. Solo lectura: no toca `data/`, ni perfiles,
ni la corrida de T31. Lo usa la skill `eim-auditoria`.
"""

from __future__ import annotations


def opp(oid: str, cat: str, title: str, evidence: str, route: str, ref: str,
        usdt: float | None = None, r_op: float | None = None) -> dict:
    """La forma de una oportunidad del informe, común a todas las palancas.

    `route` es la **vía** (`auto`, `variante`, `◆`, `cerrada`, `esperar`): lo que la sesión puede
    hacer con ella sin reabrir una decisión del usuario. El impacto es lo que la palanca habría
    cambiado en la muestra observada, en USDT y en R por operación: una cota, no una promesa.
    """
    return {"id": oid, "category": cat, "title": title, "evidence": evidence, "route": route,
            "ref": ref, "impact_usdt": usdt, "impact_r_per_op": r_op}
