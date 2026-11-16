# T170 — Pre-registro `cantera_v1` (2026-11-16)

> **En pausa (2026-11-16, después de la aprobación):** el usuario pidió en la sesión de T169 que
> prospectos nuevos de T177 reemplacen a los descartados y entren en v1, del mismo agente si emite
> variables usables. La lista de 29 de esta nota es un **borrador**: no está en `main` y no ha
> operado nadie, así que se rehace con la lista final (calibración, huella y gate), y esa lista
> vuelve a aprobarse antes de fusionar y encender. El constructor ya admite informes de examen y
> temas adicionales (`v2/scripts/t170_prereg.py --exam --themes --reserve`). Queda por decidir si
> son 14 reemplazos (familia de 43 y m = 50) o 16 (45 y reserva de 5).

**Modo: SIMULADO.** El archivo vinculante es `v2/eim/validation/prereg/prereg_cantera_v1.json`. Su
huella SHA-256 está fijada en `v2/eim/nursery/prereg.py::PUBLISHED`, y el commit `a9cefd6` es
anterior a la primera operación de la cantera. Esta nota lo resume; si hay diferencias, manda el
JSON. Cualquier cambio a mitad de fase solo puede ser `cantera_v2`, con reloj nuevo.

## Decisiones del usuario (◆, 2026-11-16)

1. **Las cuatro reglas imposibles.**
   - Se rediseñaron `estructura_ruptura` (sin filtro de convicción, cero parámetros) y
     `tec_acuerdo_marcos` (marcos de 1 h y 4 h, que son los que existen con base 1 h).
   - Las dos se re-examinaron con la misma ficha de T169 y los contextos ya guardados, sin
     regenerarlos (`v2/reports/t170_reexamen.md`). Las dos siguen:
     - `estructura_ruptura`: 25,6 operaciones al mes, scalping, 0,153 R.
     - `tec_acuerdo_marcos`: 37,6 operaciones al mes, scalping, 0,145 R.
   - Las dos de Elliott se dan de baja: arreglarlas exige una versión nueva del agente (BACKLOG).
2. **Los gemelos de `regime`** cuentan como dos prospectos dados de baja.
3. **Bandas.** Manda la banda medida y las plantillas de salida no cambian. Los 11 sin historia
   usan la banda declarada hasta su examen físico hacia adelante.
4. **Familia propia**, con m de e-BH = los que entran + las 7 plazas de reserva.
5. **Pre-registro completo aprobado.** Hay permiso para fusionar y encender la cantera hoy, con el
   gate en verde.

## Familia

- **Entran 29:**
  - 16 supervivientes con historia;
  - 11 sin historia: bots ×2, derivatives ×4, liquidations ×3 y microstructure ×2;
  - las 2 rediseñadas.
- **No entran 14,** dados de baja en el examen físico. No cuentan en m: nunca se mide su
  rendimiento.
- **m = 36 y techo 50** (43 inscritos + 7 de reserva). Una baja hacia adelante sigue contando,
  con e = 0.
- **Temas:**
  - tendencia: 11;
  - reversión: 8;
  - derivados: 7 (con las liquidaciones);
  - consenso: 3.
- **Hermano simple** (complejo = más parámetros que la base viva de su agente):
  - `pa_patron_zona` y `pa_bos_patron` → `pa_bos`;
  - `deriv_oi_tendencia` y `deriv_saturacion` → `deriv_funding_contrario`;
  - `micro_absorcion` → `micro_ofi`.

## Escalafón (`v2/eim/nursery/ladder.py`)

Las etapas solo cambian en las revisiones fijas: los días 30, 61, 91, 121, 152 y 182 desde el alta.

- **Hipótesis primaria:** H0 E[d̃] ≤ 0, con d̃ = d recortada a ±3 R. Se prueba con un e-proceso
  mezcla por apuestas (λ = 0,1…0,9).
- **Promesa:**
  - beneficio neto > 0;
  - ninguna operación > 40 % del beneficio;
  - hermano simple: z de Welch con α = 0,10; a empate, asciende el simple;
  - contribución marginal: con ρ > 0,7, tiene que aportar por encima;
  - después, e-BH con q = 0,10 y m = 36.

  Quien no cumple los requisitos entra a e-BH con e = 0, y el e-valor de quien asciende queda
  congelado, también si luego se da de baja. Así la FDR sigue ≤ q aunque se mire seis veces.
- **Baja:**
  - drawdown por encima del tope calibrado, de 13 a 21 % según las operaciones esperadas;
  - futilidad: cota superior < +0,10 R, con z(1 − 0,10/6) y n ≥ 30;
  - 60 días sin operar, sin contar los días con el marco cerrado;
  - claramente negativo al salir de guardería;
  - examen físico hacia adelante (solo los sin historia);
  - fecha límite.
- **Primer equipo,** solo el día 182 (`ladder_final.py`):
  - StepM con FWER 0,05 sobre la familia, bajas incluidas;
  - DSR ≥ 0,95 con N efectivo (grupos con ρ ≥ 0,7); el del N nominal se declara al lado;
  - ≥ 2 regímenes;
  - orden de los meses 1–3 frente a los 4–6;
  - V1, V4, V5 y V6.

  Después, ◆ T172: el usuario confirma o veta.

## El precio y la potencia, declarados (`v2/reports/t170_calibracion.json`)

- **Bajo la nula global,** e-BH deja de media 0,011 promesas falsas en la fase, y P(≥ 1) = 1,0 %,
  en 10 000 réplicas con el modelo de los gemelos. Es una cota superior.
- **Potencia de un ascenso en solitario** (e ≥ 360), con σ = 1 R:

  | Ventaja | Operaciones | Potencia |
  |---|--:|--:|
  | +0,25 R | 250 | 60 % |
  | +0,25 R | 400 | 90 % |
  | +0,50 R | 100 | 85 % |
  | +0,10 R | 650 | 11 % |

  Es el costo de poder mirar sin pagar por mirar. No es una puerta de potencia: nadie se cierra
  por «no habría n».
- **El control al azar** (prueba con 1 000 semillas y m = 1) llega a promesa el 2,8 % de las
  veces, por debajo del α de 10 %.

## Arranque

La cantera solo corre con los 29 del pre-registro y sus huellas. Si alguna no coincide, la mesa
se bloquea y lo dice en `GET /v2/nursery`; la API no se cae.

El alta es el primer cálculo con `EIM_NURSERY=1` posterior a `not_before` (2026-11-16T21:00Z), y
queda anotada en `data/paper_cantera.duckdb`, en la tabla `nursery_prereg`.
