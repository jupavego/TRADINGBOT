"""Banco de salidas de la fase 22 (T131): mide cualquier política de salida sobre las MISMAS
entradas, con los mismos costos y sin margen para ajustar después de ver los resultados.

- `policy`: la interfaz pura `ExitPolicy` y los adaptadores M0 (escalera) y M1 (TP/BE+/tiempo).
- `bench`: la corrida emparejada con tamaño fijo y sin la memoria de los perfiles.
- `metrics`: las métricas de §5.3 (devolución desde el MFE, CVaR 95 %, riesgo de ruina…).
- `walkforward`: pliegues de 12 + 3 meses con purga y embargo (E1).
- `stats`: bootstrap por días, Romano-Wolf (E3) y PBO por CSCV.
- `select`: el objetivo de selección pre-registrado (E2).
- `costs`: el estrés de costos (E4a).
- `prereg`: el archivo inmutable con la rejilla, los tramos y los criterios, con su huella.

T132 añade las políticas nuevas implementando `ExitPolicy`; el banco no cambia.
"""
