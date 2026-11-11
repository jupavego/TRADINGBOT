"""Auditoría periódica de rentabilidad y calibración (T159, fase 25).

Convierte el diagnóstico manual de la fase 24 en un comando repetible y barato de leer:

    python -m eim.analytics.audit [--api http://127.0.0.1:8000] [--data-dir data]
                                  [--out reports/audit] [--sin-red] [--ledger libro.csv]

Escribe `reports/audit/audit_AAAA-MM-DD.{json,md}` y saca por consola un resumen de ≈ 25 líneas
con las diferencias frente a la auditoría anterior. Solo lectura: no toca `data/`, ni perfiles,
ni la corrida de T31. Lo usa la skill `eim-auditoria`.
"""
