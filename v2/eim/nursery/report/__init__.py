"""Informe mensual de ojeo y retroalimentación de la cantera (T172). SIMULADO.

Informa y propone; **no cambia pesos ni parámetros por sí solo** (nota de T167 §6 y §9.4):

- `source`: lee el libro de la cantera (`paper_cantera.duckdb`, en vivo de solo lectura o la copia
  de seguridad más reciente) y, si hace falta, el precio y los regímenes. Toda la E/S vive aquí.
- `rows`: del libro a las entradas del escalafón pre-registrado (`ladder.evaluate`), puro.
- `measures`: tabla por prospecto, temas, nativo frente a genérico, N efectivo, persistencia,
  PBO descriptivo y señales tempranas (volatilidad y drawdown), puro.
- `feedback`: lo que vuelve a la biblioteca (tres veredictos), a los agentes (BACKLOG), al ciclo
  de mejora (§9.2–9.3), a la síntesis (informatividad para T150), las graduaciones con el recorte
  de Harvey-Liu (`haircut`) y el cierre de la fase, puro.
- `render` / `run`: el informe `reports/nursery/cantera_<fecha>.{md,json}` y su resumen
  `reports/nursery/latest.json`, que lee la auditoría semanal (T159).

Diseño: `PLAN/notas/T167_cantera.md` §6, §9 y §10; ficha `PLAN/T172.md`.
"""
