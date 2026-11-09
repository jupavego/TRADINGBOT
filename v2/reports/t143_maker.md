# T143 — La entrada maker frente a la taker, emparejada (entregable 1)

Modo: **SIMULADO** · BTCUSDT · banco `C:/Users/jo/Desktop/JP/TRADINGBOT/v2/backups/t131_banco` · marcos 15m, 1h, 4h · camino de precios 15m · pre-registro `PLAN/notas/T143_preregistro_maker.md` (commit `97f8174`, anterior a todo cálculo) · generado 2026-11-09T16:46:19+00:00 en 335 s.

**Nada de este informe cambia un perfil ni habilita dinero real.** No pasa por la puerta de T49, no reclama ventaja y no reabre T139: mide un costo de ejecución con el criterio escrito de antemano.

> **Dos decisiones de contabilidad posteriores al pre-registro, las dos en contra del brazo maker.** (1) **Denominador común:** el motor divide por el riesgo *realizado* (`|llenado − SL|`), así que una límite a mejor precio infla su R por aritmética; todas las cifras de aquí dividen por el riesgo **planeado** (`|entry − SL|`), idéntico en los dos brazos. (2) **Estrés de cola (§5):** el motor llena si la vela *toca* el nivel, que es la hipótesis optimista; el estrés exige que el precio **pase** del nivel. Se añaden porque sin ellas la medición se engaña sola, y las dos solo pueden hacer que maker salga peor.

## 1. Veredicto

**SE ADOPTA** la entrada maker: el costo baja 0.0432 R, el neto por intento mejora +0.0422 R con IC95 % [+0.0417, +0.0427] y el signo aguanta los tres plazos y los años.

| Criterio del pre-registro §4 | Umbral | Medido | ¿Pasa? |
|---|---|--:|---|
| 1. El costo baja de verdad | ≥ 0,0400 R | 0.0432 R | ✓ |
| 2. El neto por intento no empeora | IC95 % inferior ≥ 0 | +0.0417 R | ✓ |
| 3. El signo aguanta plazos y años | sin cambio de signo | estable | ✓ |

**El veredicto aguanta el estrés de cola** en todos los niveles probados (§5): exigir que el precio pase del nivel no lo cambia. Al nivel más duro (5 pb, 84.9 % de llenado) el ahorro de ejecución sigue siendo +0.0384 R una vez descontado lo que aporta no operar, que es la comparación que vale.

## 2. Las cifras que deciden (lectura A: por intento)

Las mismas **224814** decisiones en los dos brazos, con `fill_h` = 1 vela y 75 parejas descartadas por quedar sin resolver al final del camino. Una orden límite que no se llena cuenta **R = 0**: no es una operación que sale en tablas, es una decisión que no se ejecutó.

| | taker (hoy) | maker |
|---|--:|--:|
| Intentos | 224814 | 224814 |
| Operaciones que existieron | 224437 (99.8 %) | 223870 (99.6 %) |
| No llenadas | — | 502 |
| Objetivo alcanzado sin llenar | — | 50 |
| **E[R] neto por intento** | **-0.1925** | **-0.1503** |
| E[R] bruto por intento | -0.0013 | -0.0023 |
| Costo en R por intento | 0.1912 | 0.1480 |
| · comisiones | 0.1279 | 0.0861 |
| · deslizamiento | 0.0625 | 0.0610 |
| · funding | +0.0009 | +0.0009 |

**ΔE[R] neto por intento (maker − taker): +0.0422 R**, IC95 % bootstrap emparejado [+0.0417, +0.0427], n = 224814.

### Cuánto de esto es ahorro y cuánto es no operar

Abstenerse sube E[R] por sí solo: una orden que no se llena aporta R = 0 y el intento medio pierde. Hay que separarlo del ahorro de ejecución, o el brazo que opera menos parece mejor por el motivo equivocado.

| De dónde sale el +0.0422 R | R |
|---|--:|
| Ahorro de ejecución (lo que se persigue) | +0.0417 |
| No operar (0.25 pp menos de llenado) | +0.0005 |

Al plazo que decide, no operar solo aporta el 1 % del total: **el veredicto es ahorro de comisión, no abstención**.

### Cuánto de esto era el denominador

Con el riesgo **realizado** —el que usa el motor— las mismas operaciones dan -0.1922 R (taker) y -0.1503 R (maker), es decir ΔE[R] +0.0419 R. El riesgo medio realizado es 1.051 % del precio en taker y 1.051 % en maker. La diferencia entre las dos lecturas es la inflación aritmética que el denominador común elimina.

## 3. Lectura B, descriptiva: lo que se consigue cuando se consigue

Solo sobre las operaciones que existieron en cada brazo. **No decide**: los denominadores no son el mismo.

| | taker | maker |
|---|--:|--:|
| n | 224437 | 223870 |
| E[R] neto por llenada | -0.1928 | -0.1509 |
| Costo en R por llenada | 0.1916 | 0.1486 |
| Acierto | 46.9 % | 47.4 % |
| Factor de beneficio | 0.680 | 0.740 |

## 4. Estabilidad

### Los tres plazos de la rejilla

| `fill_h` | Llenado | Costo R taker | Costo R maker | ΔE[R] neto | IC95 % |
|---|--:|--:|--:|--:|---|
| 0.5 velas | 99.5 % | 0.1912 | 0.1479 | +0.0421 | [+0.0416, +0.0427] |
| 1 vela **(decide)** | 99.6 % | 0.1912 | 0.1480 | +0.0422 | [+0.0417, +0.0427] |
| 2 velas | 99.7 % | 0.1912 | 0.1481 | +0.0419 | [+0.0414, +0.0424] |

### Año a año (plazo que decide)

| Año | n | ΔE[R] neto por intento |
|---|--:|--:|
| 2023 | 48459 | +0.0388 |
| 2024 | 52604 | +0.0305 |
| 2025 | 49671 | +0.0388 |
| 2026 | 74080 | +0.0550 |

## 5. Estrés de cola: ¿y si hay que pasar del nivel, no solo tocarlo?

`_limit_fill` del motor da la orden por llenada cuando la vela **toca** el precio. Una orden en reposo necesita que el precio la **atraviese**, o estar al frente de la cola; medir eso de verdad es T79, y hasta entonces la hipótesis del motor es la optimista. Aquí se exige que el nivel se pase en `n` puntos básicos. **Solo puede empeorar a maker**, y por eso se añade aunque no estuviera en el pre-registro.

La columna **de no operar** separa lo que ΔE[R] gana por abstenerse de lo que gana por ahorrar ejecución: bajar el llenado sube E[R] por sí solo, porque el intento medio pierde. **Lo que valida el estrés es la columna de ejecución**, no el total.

| Paso exigido | Llenado | Costo R maker | ΔE[R] neto | de no operar | de ejecución | IC95 % | ¿Adopta? |
|---|--:|--:|--:|--:|--:|---|---|
| 1 pb | 94.7 % | 0.1389 | +0.0416 | +0.0099 (24 %) | +0.0317 | [+0.0402, +0.0429] | sí |
| 5 pb | 84.9 % | 0.1207 | +0.0672 | +0.0288 (43 %) | +0.0384 | [+0.0648, +0.0695] | sí |

## 6. Lectura secundaria: con «una viva por estrategia» (descriptiva)

Con la regla real del libro los dos brazos **dejan de ver las mismas decisiones**: si la límite no se llena, la estrategia queda libre antes y toma otras. Por eso no decide; enseña qué le pasaría al libro.

| | taker | maker |
|---|--:|--:|
| Operaciones | 42410 | 42288 |
| E[R] neto por intento | -0.2082 | -0.1651 |
| Costo en R por intento | 0.1997 | 0.1546 |

## 7. Control de realidad en el libro vivo (confundido, no es evidencia)

Cada estrategia elige su tipo de orden, así que esto **no compara iguales**: sirve para ver que los órdenes de magnitud cuadran, nada más.

| Tipo | n | E[R] neto | Costo R | Acierto |
|---|--:|--:|--:|--:|
| `market` | 136 | -0.1607 | 0.1369 | 71.3 % |
| `limit` | 78 | -0.0729 | 0.1045 | 57.7 % |

## 8. Lo que esta medición no cubre

- **No hay 15 m.** El banco de T131 se pre-registró con marcos 15m, 1h, 4h y no tiene ni una operación de 15 m, que es donde el stop está más cerca y el costo más pesa (T136 §1). Esta medición **no dice nada** de ese marco.
- **El camino de precios es de 15m.** Dentro de una vela no se sabe el orden de los extremos, así que el llenado es el que el motor supone, igual en los dos brazos.
- **No mide ventaja.** Si el bruto se mueve, no es porque se prediga mejor.
- **El modelo supone que entrar a mercado casi no desliza** (0.1 pb de base y sin término de volatilidad, frente a 1 pb más volatilidad al salir), así que todo el ahorro que se mide es de **comisión**. Si entrar desliza más de lo supuesto, esta medición **subestima** a maker: el sesgo va a favor del veredicto, no en contra.
- **Adoptar maker cambia la huella de versión** de todas las estrategias afectadas (`versioning.py`) y reinicia la cuenta de operaciones en vivo de V5. Es ◆ del usuario.
