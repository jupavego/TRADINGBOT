"""Renta fija: modelos mínimos y puros (T100). Sin red, sin disco, sin estado.

Por qué existe: aplicar indicadores técnicos al precio de un bono no dice nada de él. Un bono se
entiende por su **curva** (a qué tipo descuenta cada plazo), su **duración y convexidad**
(cuánto se mueve su precio si la curva se mueve) y su **carry/roll-down** (qué rinde si la curva
no se mueve). Estos módulos dan esas piezas como funciones puras con pruebas contra valores
publicados; no son una clase de activo completa (eso lo decide la ◆ de T100).

- `bond`: flujos, precio ↔ rendimiento, duración (Macaulay y modificada), convexidad, DV01.
- `curve`: Nelson–Siegel y Svensson (ajuste por mínimos cuadrados), interpolación y
  *bootstrap* de tipos cero desde bonos o desde la curva par.
- `carry`: carry y roll-down con la curva quieta, exactos para un cupón cero y por
  revalorización para un bono con cupón.
- `proto`: los dos agentes de prueba (curva y carry), en modo ANÁLISIS y sin registrar.
"""
