# T170 — Pre-registro `cantera_v1` (2026-11-16/17)

**Modo: SIMULADO.** El archivo vinculante es `v2/eim/validation/prereg/prereg_cantera_v1.json`. Su
huella SHA-256 está fijada en `v2/eim/nursery/prereg.py::PUBLISHED`. Esta nota lo resume; si hay
diferencias, manda el JSON. Cualquier cambio a mitad de fase solo puede ser `cantera_v2`, con
reloj nuevo.

## Cómo se llegó a la familia (◆ del usuario)

1. **2026-11-16, en esta sesión:**
   - se rediseñan `estructura_ruptura` y `tec_acuerdo_marcos`, y se re-examinan
     (`v2/reports/t170_reexamen.md`);
   - los gemelos de `regime` cuentan como dos;
   - manda la banda medida, sin tocar las plantillas;
   - familia propia, con m = los que entran + las plazas de reserva;
   - se aprueba el pre-registro de 29 (`a9cefd6`).
2. **Después, en la sesión de T169:** 50 obras nuevas y prospectos nuevos que reemplazan a los
   descartados. Entran en v1, del mismo agente si emite variables usables (T177). `regime` queda
   excluido y sus dos plazas van a `elliott` y a `bots`.
3. **Rediseños duplicados:** el usuario eligió las versiones de T177, `estructura_ruptura_sc02` y
   `tec_acuerdo_tres_marcos`. El rediseño en su sitio de T170 se revirtió (`a6f187e`), y el
   re-examen de T170 queda solo como registro.
4. **El examen físico de T177** (`v2/reports/t177_examen_fisico.md`) descartó
   `elliott_tendencia_dow`: 4,7 operaciones al mes, y la banda pide 5. Su plaza vuelve a la reserva.

Ninguna operación de la cantera se hizo antes de este pre-registro. La lista de 29 solo existió
en la rama y nunca operó.

## Familia final

- **Entran 42:**
  - 16 supervivientes de T169;
  - 12 sin historia: los 11 de T169 y `bots_contrario`;
  - 14 reemplazos con historia, examinados por T177.
- **Descartes: 17.** Son 16 de T169 y 1 de T177, con su huella en los expedientes (clave
  `discarded`). No cuentan en m: nunca se mide su rendimiento.
- **Reserva y m:** 8 plazas de reserva hasta el techo de 50, así que **m = 50**. Una baja hacia
  adelante sigue contando, con e = 0.
- **Temas:**
  - tendencia: 18;
  - reversión: 12;
  - derivados: 7;
  - consenso: 5.
- **Hermano simple** (complejo = más parámetros que la base viva de su agente):
  - `pa_patron_zona` y `pa_bos_patron` → `pa_bos`;
  - `deriv_oi_tendencia` y `deriv_saturacion` → `deriv_funding_contrario`;
  - `micro_absorcion` → `micro_ofi`;
  - `ema_retroceso_12h` → `ema_precio_200`;
  - `niveles_redondos` → `niveles_rebote`;
  - `tec_compresion_bb_12h` → `tec_acuerdo_tres_marcos`.
- **Banda semanal:** ningún prospecto es semanal. Con las plantillas vigentes ninguno pasa de 62 h
  de tenencia mediana. Tener semanales de verdad exigiría otra plantilla (BACKLOG T177 (1),
  `cantera_v2`).

## Escalafón (`v2/eim/nursery/ladder.py`)

Las etapas solo cambian en las revisiones fijas: los días 30, 61, 91, 121, 152 y 182 desde el alta.

- **Hipótesis primaria:** H0 E[d̃] ≤ 0, con d̃ = d recortada a ±3 R. Se prueba con un e-proceso
  mezcla por apuestas (λ = 0,1…0,9).
- **Promesa:**
  - beneficio neto > 0;
  - ninguna operación > 40 % del beneficio;
  - hermano simple: z de Welch con α = 0,10; a empate, asciende el simple;
  - contribución marginal: con ρ > 0,7, tiene que aportar por encima;
  - después, e-BH con q = 0,10 y m = 50.

  Quien no cumple los requisitos entra a e-BH con e = 0, y el e-valor de quien asciende queda
  congelado, también si luego se da de baja. Así la FDR sigue ≤ q aunque se mire seis veces.
- **Baja:**
  - drawdown por encima del tope calibrado, de 9,6 a 20,9 % según las operaciones esperadas;
  - futilidad: cota superior < +0,10 R, con z(1 − 0,10/6) y n ≥ 30;
  - 60 días sin operar, sin contar los días con el marco cerrado;
  - claramente negativo al salir de guardería;
  - examen físico hacia adelante (los 12 sin historia);
  - fecha límite.
- **Primer equipo,** solo el día 182 (`ladder_final.py`):
  - StepM con FWER 0,05 sobre la familia, bajas incluidas;
  - DSR ≥ 0,95 con N efectivo (grupos con ρ ≥ 0,7); el del N nominal se declara al lado;
  - ≥ 2 regímenes;
  - orden de los meses 1–3 frente a los 4–6;
  - V1, V4, V5 y V6.

  Después, ◆ T172: el usuario confirma o veta.

## El precio y la potencia, declarados (`v2/reports/t170_calibracion.json`)

- **Bajo la nula global,** e-BH deja de media 0,0068 promesas falsas en la fase, y P(≥ 1) = 0,7 %,
  en 10 000 réplicas con el modelo de los gemelos. Es una cota superior.
- **Potencia de un ascenso en solitario** (e ≥ 500), con σ = 1 R:

  | Ventaja | Operaciones | Potencia |
  |---|--:|--:|
  | +0,25 R | 250 | 56 % |
  | +0,25 R | 400 | 88 % |
  | +0,50 R | 100 | 82 % |
  | +0,10 R | 650 | 10 % |

  No es una puerta de potencia: nadie se cierra por «no habría n».
- **El control al azar** (prueba con 1 000 semillas y m = 1) llega a promesa el 2,8 % de las
  veces, por debajo del α de 10 %.

## Arranque

La cantera solo corre con los 42 del pre-registro y sus huellas. Si alguna no coincide, la mesa
se bloquea y lo dice en `GET /v2/nursery`; la API no se cae.

El alta es el primer cálculo con `EIM_NURSERY=1` posterior a `not_before` (2026-11-17T02:00Z), y
queda anotada en `data/paper_cantera.duckdb`, en la tabla `nursery_prereg`.
