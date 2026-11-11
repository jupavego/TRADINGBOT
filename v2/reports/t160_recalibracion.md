# T160 — Recalibración de las probabilidades de escenario: ninguna pasa

Generado el 2026-11-11 con `python scripts/t160_recalibracion.py`, por la cola (135 s, sin pausas).
Datos: `reports/t160_recalibracion.json`. Pre-registro: `PLAN/notas/T160_preregistro.md`, en el commit
`92f6e12`, anterior al código (`ff57281`) y a este resultado. **Modo: SIMULADO.** Análisis
histórico: no es una promesa de resultados.

## Veredicto
**No se adopta ningún método y la línea se cierra** (pre-registro §5): ni M1 ni M2 pasan Holm en el
banco, y los dos **empeoran** el Brier en vivo.

| Método | Banco: Brier bruto → recal. | d sin solape (n = 1 124) | p (1 cola) | Holm | ECE banco | Vivo: d media (n = 557) | ECE vivo | ¿Pasa? |
|---|--:|--:|--:|:-:|--:|--:|--:|:-:|
| M1 priors | 0,6263 → 0,6198 | +0,0029 [−0,0050; +0,0107] | 0,237 | no | 0,0239 → 0,0238 | **−0,0120** [−0,021; −0,003] | 0,082 → 0,088 | no |
| M2 isotónica | 0,6263 → 0,6199 | +0,0058 [−0,0029; +0,0145] | 0,096 | no | 0,0239 → 0,0193 | −0,0035 [−0,014; +0,007] | 0,082 → 0,068 | no |

Criterios (§4): (a) Holm al 5 % en el banco, (b) media de d > 0 en vivo, (c) ECE del banco que no
empeore. M1 y M2 cumplen (c) y fallan (a) y (b).

## Por qué: el sesgo que vio la auditoría es de régimen, no del modelo
| | bull | neutral | bear |
|---|--:|--:|--:|
| Banco 2023-01 → 2026-11: probabilidad media | 28,4 % | 43,7 % | 27,9 % |
| Banco: frecuencia observada | 25,6 % | 50,8 % | 23,6 % |
| Vivo oct–nov 2026: probabilidad media | 27,3 % | 44,5 % | 28,2 % |
| Vivo: frecuencia observada | 14,9 % | 45,6 % | 39,5 % |

En 3,8 años de historia las probabilidades del motor ya están **casi calibradas** (ECE 0,024; el
«bull» sobra solo 3 pp). Los 12 pp de la primera auditoría (T159) salen de cuatro semanas bajistas:
corregirlos con la historia **empuja en el sentido contrario** al régimen y empeora el vivo. Un
recalibrador no puede adivinar el régimen, y eso es predecir la dirección, que T139 ya cerró.

## Qué cambia
- Nada en el pronóstico ni en el panel. El panel sigue diciendo que las probabilidades no superan a
  la caminata aleatoria (Brier skill ≈ 0).
- La auditoría periódica deja de proponer recalibrar: el aviso de escenario descalibrado pasa a
  informativo («régimen», vía cerrada por T160).
- La familia de calibración queda en 2 intentos, ambos fallidos. Reabrir exige un método nuevo con
  pre-registro propio, no otra variante de estos dos con los mismos datos.

## Notas de método
- Banco: 8 373 pronósticos walk-forward (un origen cada 4 velas); 7 868 con ajuste disponible
  (mínimo 500 resultados terminados, reajuste cada 250). Submuestra sin solape: 1 de cada 7 (28 velas ≥ 25).
- Vivo: 557 pronósticos persistidos de la copia `eim_20261111-000001`, ninguno de backfill. El modelo
  congelado se ajustó solo con los 8 280 resultados del banco **terminados antes** del primer
  pronóstico en vivo, para que sea fuera de muestra puro (§3).
- Los pronósticos en vivo llevan plan y derivados; los del banco, el motor solo (como en T19). Es la
  misma diferencia que ya tiene `/v2/calibration`.
