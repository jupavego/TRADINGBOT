# T160 — Pre-registro de la recalibración de escenarios (fijado antes de calcular)

**Modo: SIMULADO.** Este archivo se confirma en un commit **anterior** a cualquier resultado. Nada
de lo que sigue se cambia después de mirar cifras; si algo resulta inaplicable, se dice en el
informe y el intento cuenta como fallido.

## 1. Qué se recalibra
Las probabilidades de los tres escenarios (`bull`, `neutral`, `bear`) que publica el pronóstico
(`eim/forecast/scenarios.py`, motor `BaseEngine`, horizonte 25 velas, 200 trayectorias). El
resultado de cada pronóstico es el de `eim/forecast/calibration.evaluate_forecast` sin cambios.
Ni bandas, ni trayectorias, ni la síntesis.

## 2. Familia de Holm: propia de calibración, 2 intentos (◆ de T160, 2026-11-11)
- **M1 · corrección de priors por escenario.** `w_i = frecuencia observada_i / probabilidad media_i`
  en la ventana de ajuste; `p'_i ∝ p_i · w_i`, renormalizado.
- **M2 · isotónica por escenario.** Regresión isotónica creciente (PAV) de `1[realizado = i]` sobre
  `p_i` en la ventana de ajuste, para cada escenario; `p'_i` = valor ajustado (interpolación lineal
  entre nodos, recorte a [0,01; 0,98]) y renormalizado para que sumen 1.
- No se añade ningún método más a esta familia después de ver resultados.

## 3. Datos y ajuste sin mirar el futuro
- **Banco:** `backups/t131_banco`, BTCUSDT 1 h (2023-01 → 2026-11), pronósticos walk-forward con
  `eim/forecast/backfill.py` (contexto 1 500 velas, origen inicial 150), **un origen cada 4 velas**
  como T150.
- **Walk-forward:** en el origen `t` solo se usan para ajustar los pronósticos cuyo horizonte ya
  terminó (`made_at + 25 velas ≤ t`). Ventana de ajuste **expansiva**; mínimo **500** resultados
  antes de la primera predicción recalibrada; reajuste cada **250** orígenes. Antes de ese mínimo
  no hay predicción y esos orígenes no cuentan para nadie (ni bruto ni recalibrado).
- **En vivo:** los pronósticos persistidos de la copia diaria más reciente
  (`backups/eim_<fecha>/reports.duckdb`, BTCUSDT 1 h, horizonte 25), evaluados contra las velas del
  almacén con el **modelo ajustado sobre el banco completo y congelado**. Es fuera de muestra puro.

## 4. Métrica y criterio de adopción
- **Métrica principal:** Brier de 3 clases (como `summarize`). Diferencia emparejada
  `d = Brier(bruto) − Brier(recalibrado)` por origen; positivo = mejora.
- **Inferencia:** los horizontes se pisan, así que la prueba usa la **submuestra sin solape**
  (un origen de cada 25 velas = cada 7 orígenes del banco, empezando por el primero evaluable):
  t de una cola sobre la media de `d`; **Holm al 5 %** sobre los 2 intentos.
- **Se adopta un método solo si:** (a) pasa Holm en el banco; (b) en vivo la media de `d` es > 0
  (no se exige significación: con ≈ 22 horizontes independientes la potencia es mínima y se dice);
  (c) el ECE del banco no empeora. Si pasan los dos, se adopta el de mayor media de `d` en el banco.
- **Secundarias, solo informativas:** Brier skill frente a la caminata aleatoria, ECE, acierto del
  escenario más probable, probabilidad media frente a frecuencia observada.
- **Hipótesis nula esperada:** si el sesgo de priors es estable, M1 mejora un poco el Brier y no la
  dirección; si no lo es, ninguno pasa. Una recalibración no puede crear acierto direccional.

## 5. Qué pasa con el resultado
- **Adopción no antes del cierre de T31 (2026-11-27)**, aunque pase (◆ de T160). Entonces la
  recalibración se aplica a lo que publica el panel con su versión y su fuente declaradas.
- Si ninguno pasa, el panel sigue diciendo que las probabilidades no superan a la caminata aleatoria
  y la línea se cierra: no se prueban más métodos con estos datos.
