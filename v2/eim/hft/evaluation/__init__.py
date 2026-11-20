"""Marco de evaluación del carril HFT (T80): etiquetas, particiones, métricas y ridge. Puro.

`labels` (Δmid con la reacción medida, dirección neta de costos, triple barrera, llenado de cola
pesimista) · `splits` (días contiguos con purga y embargo, walk-forward) · `metrics` (IC de
Spearman por día, acierto balanceado, Brier/pinball, pb netos con IC por bloques de día) ·
`ridge` (regresión conjunta en forma cerrada) · `prereg` (criterios congelados antes de mirar los
resultados) · `attempts` (todos los intentos y Holm sobre la familia completa).
"""
