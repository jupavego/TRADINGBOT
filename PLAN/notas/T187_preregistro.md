# Pre-registro T187–T189 — asimetría ganancias/pérdidas (`t187_asimetria_v1`)

**Congelado el 2026-11-18, antes de medir ninguna de estas reglas.** Huella
`0d4977fad3a63bb403ee6938578ca5332f7503fca18decec809686d2aafcd286` (`eim/paper/asym/prereg.py`,
`fingerprint()`; `tests/paper/asym/test_prereg.py` falla si cambia sin versión nueva).
**Modo: SIMULADO.** Nada de esto habilita dinero real.

## Por qué

Diagnóstico vivo del 18-nov (`claude/asimetria_ganancias_perdidas_2026-11-18.md` del proyecto):
86,2 % de acierto con equilibrio en 86,0 %; ganadora media +0,121 R, perdedora −0,746 R; la
escalera corta las ganadoras en ~+0,10 R (máxima +0,43 R) y 7 stops completos a −1,17 R borran el
resto; costo 0,143 R por operación frente a un bruto de +0,145 R; las perdedoras llevan más
tamaño. **Esas 87 operaciones quedan fuera de la medición**: solo cuentan las abiertas desde
`2026-11-19T00:00:00Z`.

## Qué se mide (cada operación viva frente a lo que habría pasado con la regla)

| Regla | Población | Contrafactual |
|---|---|---|
| **T187a** pérdida acotada a 1 R con costos | operaciones de perfil del libro fijo | tamaño × riesgo/(riesgo + costo) — **solo informa**: ya decidida, se enciende sola el 28-nov |
| **T187b** una idea, un solo riesgo | ídem | en un perfil, de las entradas en la misma vela y el mismo sentido solo cuenta la primera (la de `opened_t` menor; empate: mayor peso, luego `ledger_id`) |
| **T187c** el peso no sube por rasguños | ídem | peso tope 1,0 salvo `n ≥ 20` y `m − 1·se > 0` de los cierres propios previos de esa estrategia@marco en ese perfil |
| **T188** corredor | ídem | 50 % sale como salió (escalera); 50 % sigue con el SL inicial, break-even + costo tras +1 R y stop a 1 R del extremo; plazo 2 d (15 m), 5 d (1 h), 14 d (4 h); costo = el de la operación real; sin funding extra |
| **T189** límite por defecto | ideas vivas a mercado (sombra), por marco | la misma idea como límite al precio pedido, 1 vela de vigencia (`maker_ab.pair_up`); la no ejecución cuenta como 0 R |

Unidad: diferencia emparejada en **R unitario del perfil** (`r × peso`: el R del libro va sobre el
riesgo de esa operación, que ya incluye el peso, y un cambio de tamaño no se vería en `r`); en
T189, sobre el riesgo planeado (`_p` de T143). Las cifras en USDT se publican, pero no deciden.

## Regla de decisión

- **Tres miradas fijas** a 28, 56 y 84 días: **2026-12-17, 2027-01-14 y 2027-02-11** (00:00 UTC).
  Ninguna otra mirada decide. Cada una usa un IC al 98,33 % (α = 0,05/3), bootstrap por bloques de
  día, 5 000 remuestras, semilla 187.
- Mínimos para decidir: 60 operaciones emparejadas y 15 días distintos (T187b, T187c, T188); 200
  ideas emparejadas por marco (T189).
- **PASA** si la diferencia media es > 0 y el límite inferior del IC es > 0. En T189 además: el
  costo baja ≥ 0,04 R y el signo es el mismo en las dos mitades de la muestra (criterio de T143).
- **NO PASA** si el límite superior es < 0, o si en la tercera mirada no pasó.
- Si no, **EN CURSO** hasta la mirada siguiente. **El primer veredicto queda escrito y no se
  revisa** (`data/paper/asym/verdicts.json`).

## Qué pasa con cada veredicto (fase 3)

- **Se adopta sola** (costo y riesgo, regla del usuario de T143): T187b, T187c y T189 por marco.
  El instante de adopción es el siguiente 00:00 UTC después del veredicto y nunca antes del cierre
  de T31 (2026-11-28). Solo se aplica a decisiones posteriores a ese instante (los libros no se
  reescriben hacia atrás). Queda en `data/paper/asym/adopted.json`. `EIM_ASYM_ADOPT=0` lo impide.
- **La decide el usuario**: T188, porque cambia la salida (T139 P1). Pasar no la enciende.
- Un NO PASA deja lo de hoy y se anota.

## Fase 2 (◆ del usuario 2026-11-18), fuera de la medición

Desde `EIM_PAPER_PHASE2_FROM` (por defecto el cierre de T31, 2026-11-28 00:00 UTC), para las
decisiones posteriores a ese instante y en los cuatro perfiles:
- riesgo con costos (`risk_includes_costs`);
- freno gradual **en lugar del todo o nada**: riesgo ×0,5 desde −5 % y ×0,25 desde −10 %, medidos
  desde el capital al encenderse; **nunca se detiene del todo** (◆ del usuario).

## Limitaciones declaradas

- T188 se simula sobre el camino de 15 m con el orden adverso dentro de cada vela (si en la misma
  vela se toca el stop y un extremo nuevo, sale el stop); no suma funding de la parte que sigue.
- T187b toma el orden de apertura del libro (`opened_t`), que en una misma vela puede no ser el
  orden en que el libro procesó las ideas.
- T187c lee los cierres previos del libro fijo, no la memoria interna de la escalera
  (`LadderRisk`), que además incluye lo reconstruido como opinión inicial.
- Con ~3,5 operaciones de perfil al día en la portátil, 60 emparejadas llegan hacia la primera
  mirada; puede quedar EN CURSO.
