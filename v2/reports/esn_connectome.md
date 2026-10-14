# T28 — ESN con reservorio del conectoma de Drosophila: veredicto

Fecha: 2026-10-13 · Laboratorio: `v2/lab/esn_connectome/` (fuera de `eim/`) · Tablas completas: `reports/esn_connectome/results.md` · Datos: `n100.json`, `n500.json`, `n1000.json`.

## Veredicto: **NO GANA → se archiva**
El reservorio del conectoma no es mejor que un reservorio aleatorio con la misma densidad. Pasa lo mismo con N = 100, 500 y 1.000 neuronas. Todos los ESN superan por poco al cono de volatilidad (≈ +1 % en pinball), pero esa mejora la consigue igual una regresión lineal sobre rezagos, sin reservorio. No hay capacidad direccional y la operativa pierde después de costos. No se crea ningún `Engine` y no se toca nada del paquete principal.

## Qué se probó
- **Datos**: velas de 1h de BTCUSDT y ETHUSDT (2023-01 → 2026-10). Walk-forward con 1 año de entrenamiento y 6 meses de prueba, 6 pliegues por activo, es decir 12 celdas activo×pliegue con unos 1.000 orígenes sin solapamiento. Horizonte de 25 velas. Los hiperparámetros (ρ, fuga y alpha) se eligen solo con validación interna.
- **Conectoma**: FlyWire v783 (Zenodo 10.5281/zenodo.10676866, **CC BY 4.0**, atribución al FlyWire Consortium). El subgrafo voraz de 1.000 neuronas cae sobre todo en el lóbulo accesorio lateral y el GNG (circuitos premotores). El 46 % de sus neuronas son inhibidoras (GABA/Glu) y el 42 % de las aristas son recíprocas. Solo se versiona el subgrafo derivado (217 KB).
- **Variantes con la misma lectura de cuantiles**: ESN aleatorio, ESN con la topología y los pesos reales, ESN con la topología real y pesos aleatorios. Se comparan contra el cono de volatilidad, el motor base de T16 y una regresión lineal con 24 rezagos. **Kronos no se evaluó** porque no está instalado (decisión del usuario). No cambia el veredicto: el criterio de conectoma frente a aleatorio (C1) falla de todos modos.

## Resultados (pinball del retorno log terminal; resultado agregado)
| N | conectoma vs aleatorio | conectoma vs cono | conectoma vs T16 | conectoma vs lineal | cob. 50/80 | acierto dir. | neto/op |
|---|---|---|---|---|---|---|---|
| 100 | +0.22 % (IC incluye 0; 58 % de celdas) | +0.95 % ✔ | +1.08 % ✔ | +0.11 % (n.s.) | 48.6 / 79.3 % | 51.4 % (p Holm 0.43) | −13 pb [−21, −6] |
| 500 | +0.01 % (n.s.; 50 %) | +0.67 % (IC incluye 0) | +0.81 % (IC incluye 0) | −0.18 % (n.s.) | 48.6 / 78.9 % | 50.6 % (0.77) | −13 pb [−19, −8] |
| 1000 | +0.05 % (n.s.; 58 %) | +0.99 % ✔ | +1.13 % ✔ | +0.15 % (n.s.) | 48.3 / 78.9 % | 50.3 % (1.00) | −19 pb [−26, −11] |

Skill positivo = el conectoma tiene menos pérdida. ✔ = gana en ≥ 75 % de las celdas y el IC95 de la diferencia es < 0.

Criterios fijados antes de correr (ver `lab/esn_connectome/README.md`):
- **C1 (conectoma > aleatorio): falla en los tres tamaños.** Con N = 500, por ejemplo, la diferencia media es −0.004·10⁻⁴ (IC95 [−0.17, +0.15]·10⁻⁴).
- **C2 (> cono y > T16)**: se cumple con N = 100 y N = 1.000, y falla por poco con N = 500.
- **C3 (cobertura)**: se cumple en los tres.
- **C4 (económico)**: falla en los tres.

Para declarar que gana hacían falta C1, C2 y C3 a la vez.

## Lectura
1. **La biología no aporta nada medible.** Comparé la topología real contra la aleatoria y los pesos reales contra los aleatorios. Ninguna de las dos diferencias es consistente. La única significativa es «topología > aleatorio» con N = 100 (+0.35 %), que no se repite con N = 500 ni con N = 1.000, así que la trato como ruido.
2. **La pequeña mejora frente al cono no viene del reservorio.** Una regresión lineal sobre rezagos rinde igual (+0.85 % frente al cono). Esa mejora sale de modelar la escala, es decir, de predecir |residuo| (heterocedasticidad). No se predice el signo.
3. **Dirección**: el acierto está en 50–51 % en todas las variantes y el PnL neto es negativo con IC95 < 0. Esto coincide con T27 y con la única prueba financiera previa, que también fue negativa.

## Pendiente (BACKLOG)
El aprendizaje aprovechable no tiene que ver con el conectoma. Una lectura de escala (|residuo| condicionado a σ relativa, rango y volumen) mejora en ≈ 1 % el pinball del cono y del motor T16 sin perder cobertura. Es una hipótesis barata para el motor base, y habría que validarla dentro de T19 antes de integrarla.
