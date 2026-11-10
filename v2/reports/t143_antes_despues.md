# T143 — Antes y después, sobre las mismas operaciones vividas (entregable 5)

**Modo: SIMULADO.** Libro vivo leído 2026-11-10 01:37 UTC (`GET /v2/paper/ledger.csv`): 224 operaciones de perfil sin `retro`, 0 sin riesgo reconstruible. Método del diagnóstico de la fase 24 (riesgo = |pnl| / |r|, bruto = neto + costo). El «después» es un **contrafactual** sobre esas mismas operaciones, no algo vivido: el cambio no se despliega mientras T31 cuente semanas.

## 1. El número

| Paso | Operaciones | Costo medio R | Costo mediana R | E[R] neto | ± EE | E[R] bruto |
|---|--:|--:|--:|--:|--:|--:|
| Antes (vivido) | 224 | 0.123 | 0.113 | -0.150 | 0.057 | -0.027 |
| 1 · sin 15 m | 160 | 0.109 | 0.102 | -0.191 | 0.057 | -0.083 |
| 2 · + entrada maker en 1 h y 4 h | 160 | 0.092 | 0.083 | -0.174 | 0.057 | -0.083 |
| 3 · + riesgo con costo (T143 completo) | 160 | 0.083 | 0.077 | -0.153 | 0.053 | -0.070 |

## 2. Por marco

| Paso | Marco | n | Costo R | E[R] neto | ± EE | E[R] bruto |
|---|---|--:|--:|--:|--:|--:|
| Antes (vivido) | 15m | 64 | 0.160 | -0.048 | 0.140 | +0.112 |
| Antes (vivido) | 1h | 85 | 0.127 | -0.218 | 0.082 | -0.091 |
| Antes (vivido) | 4h | 75 | 0.087 | -0.161 | 0.079 | -0.073 |
| 1 · sin 15 m | 1h | 85 | 0.127 | -0.218 | 0.082 | -0.091 |
| 1 · sin 15 m | 4h | 75 | 0.087 | -0.161 | 0.079 | -0.073 |
| 2 · + entrada maker en 1 h y 4 h | 1h | 85 | 0.108 | -0.199 | 0.082 | -0.091 |
| 2 · + entrada maker en 1 h y 4 h | 4h | 75 | 0.073 | -0.146 | 0.079 | -0.073 |
| 3 · + riesgo con costo (T143 completo) | 1h | 85 | 0.096 | -0.170 | 0.075 | -0.074 |
| 3 · + riesgo con costo (T143 completo) | 4h | 75 | 0.068 | -0.132 | 0.074 | -0.065 |

## 3. Lectura

- **El costo baja de 0.123 R a 0.083 R** por operación (33% menos). No llega a los ~0,06 R que estimó el diagnóstico: el ahorro maker solo toca la comisión de entrada de las `market` de 1 h y 4 h, y el riesgo con costo escala, no elimina.
- **La esperanza neta no mejora: -0.150 → -0.153 R.** Lo que ahorran maker y el riesgo con costo lo devuelve la salida de 15 m.
- **15 m era el marco con mejor resultado vivido**: bruto +0.112 R y neto -0.048 ± 0.140 R con n = 64. Con ese error estándar no se distingue de 1 h ni de 4 h. **La sombra, con veinte veces más muestra, dice lo contrario** (tabla siguiente): 15 m es el peor marco. Lo vivido en 15 m es ruido de pocas operaciones y la salida de 15 m se sostiene, aunque en este contrafactual le cueste esperanza al libro.

| Sombra (sin peso, sin `retro`) | n | E[R] neto | ± EE |
|---|--:|--:|--:|
| 15m | 1378 | -0.344 | 0.039 |
| 1h | 436 | -0.228 | 0.054 |
| 4h | 142 | -0.311 | 0.084 |

- **T143 no crea ventaja, como decía su enunciado.** Lo que sí deja: el riesgo declarado es el real, el costo baja un tercio y se ve en el panel y en el informe semanal.

## 4. Lo que este contrafactual no cubre

- La no ejecución de las límite (0,2 % de intentos en el banco) y la selección adversa (bruto −0,001 R por intento en el banco): están medidas en `reports/t143_maker.md` §2 y son pequeñas frente al ahorro.
- Quitar 15 m también cambia el capital disponible y los topes de las demás: aquí cada operación de 1 h y 4 h se queda como se vivió.
- Las cifras son medias por operación con peso igual, como el diagnóstico; no son USDT del libro.
