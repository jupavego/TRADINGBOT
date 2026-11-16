"""La cantera (fase 27): perfiles propios de cada agente, medidos solo hacia adelante. SIMULADO.

- `prospect`: contrato `Prospect` (inmutable, con huella) y carga validada de los expedientes T167.
- `native`: qué variables de cada agente se guardan en el contexto y cómo se compactan.
- `rules/<agente>.py`: reglas nativas puras (solo ven las variables declaradas, nunca el futuro).
- `sim`: simulación de una operación (maker conservador, *markout*, funding con su frecuencia).
- `book`: cuentas propias por prospecto y control, gemelos aleatorios pareados y puerta de costo.
- `desk` / `store`: la variante del bróker que la corre (apagada por defecto, `EIM_NURSERY=0`).

Nada de esto escribe en los libros de T31 ni pesa en la síntesis.
Diseño: `PLAN/notas/T167_cantera.md`.
"""
