---
name: eim-auditoria
description: Auditoría periódica de rentabilidad, riesgo y calibración del EIM (T159, fase 25) con poco gasto de tokens. Úsala cuando se pida «auditoría», «revisión periódica», «calibración», «cómo vamos», «oportunidades de mejora/rentabilidad», al cerrar una semana de T31, o cuando la tarea programada `eim-auditoria-semanal` (lunes 03:00 UTC) la lance.
---

# Auditoría periódica EIM (desde `v2/` de la carpeta principal, rama `main`)

**Modo: SIMULADO.** La auditoría es de solo lectura: no reinicia servicios, no toca `data/`, perfiles,
catálogo ni la corrida oficial de T31. Todo lo que encuentre termina en una tarea o en una ◆, nunca
en un cambio directo.

## 0. Lo que ya está decidido (no reabrir sin el usuario)

Esto resume 158 tareas. Si un hallazgo choca con una línea de esta tabla, se informa como dato y no se propone.

| Tema | Decisión vigente | Dónde |
|---|---|---|
| Para qué sirve el sistema | **D, solo análisis** (2026-11-10). Nada de operar con edge salvo que salte un disparador | T145, `reports/t145_clase_de_ventaja.md` |
| Entradas direccionales | Cerrada con **P1** (vinculante, fecha límite 2027-05-06). Reabrir exige una fuente con ≥ 1 año de historia propia | T139 |
| Salidas | Ninguna de 87 variantes se adopta; la escalera sigue | T134 |
| Apartar el stop / filtrar por costo | Cerrada: 0 de 520 versiones | T137 |
| M8 | Se **mide** en papel (A/B), no se adopta; veredicto ≥ 2026-12-06 | T135 |
| Qué se adapta solo | **Solo costo y riesgo**, con umbral escrito en `AUTO_ADAPT` (`eim/paper/t143_config.py`) y en la corrida aparte `t143` | T143, memoria «automejora acotada» |
| Universo de resultados | Libro de los 4 perfiles, vivas, con peso, **sin `retro`** (`counts_as_result`) | T144 |
| Al cerrar T31 (2026-11-27) | Encender `risk_includes_costs` y el freno gradual; decidir si la variante t143 pasa a oficial | `PLAN/T31.md`, T136 |
| Dinero real | Imposible: puerta T27 no pasa | T27, T31 |
| Puerta alternativa | ◆ **cerrada por el usuario** (2026-11-26): no se pre-registra, ni en sombra. Las puertas lentas giran 3 y 1 vez en 98 d: nada medible | T215, BACKLOG T159 |
| Multiplicidad | Todo intento cuenta en Holm (familia 841) | T49, T139 |
| Calibración | Recalibrar cerrado: M1 y M2 fallaron su pre-registro; el motor está casi calibrado en el banco (ECE 0,024) y los desvíos en vivo son de régimen | T160 |
| Foco | Solo BTCUSDT | T122 |

**Lectura honesta de «rentabilidad»:** el bruto del libro es ≈ 0 R. Las palancas de costo y riesgo
solo **reducen la pérdida**; no crean ventaja. Lo que podría cambiar el signo son los **disparadores
de T145** (funding ≥ 4 % anual en 12 m → reabrir carry; 1 año de L2 propio → valorar microestructura)
y la calidad del análisis (calibración), que es el producto bajo la decisión D. Dilo así en el informe.

## 1. Línea base (primera auditoría, 2026-11-11, `reports/audit/audit_2026-11-11.json`)

n = 250 · E[R] −0,131 R (IC −0,233 … −0,030) · bruto −0,009 · costo 0,123 R (14,4 pb) · acierto 68,0 %
frente a un equilibrio del 77,4 % · PnL −1 674 USDT con 1 795 de fricción · entradas límite −0,050 R
frente a mercado −0,174 · 15 m es el marco menos malo (+47,6 USDT) aunque es el más caro · variante
t143 con n = 19 · funding 12 m BTC 3,54 % (**cerca** del 4 %), ETH 2,47 % · L2 propio 45 días · captura HFT
77,8 % de horas completas · calibración BTC 1 h: Brier skill −0,010, acierto direccional 40,7 %, «bull»
sobrestimado (27 % de probabilidad media frente a 15 % real).

**Segunda auditoría (2026-11-16, ya con T175):** n = 410 · E[R] −0,110 R (IC −0,179 … −0,042) ·
bruto +0,016 · costo 0,126 R · acierto 72,4 % frente a 81,1 % · PnL −2 552 USDT con 2 781 de
fricción · variante t143 **+0,011 R/op emparejada** (115 comunes; sin emparejar daba −0,032) ·
la variante sigue operando 15 m a 0,157 R vividos (agresivo 0,180) · funding 12 m BTC 3,51 % ·
calibración BTC 1 h: Brier skill −0,004, acierto direccional 46,8 %, n efectiva 29,5 («bear»
27 % frente a 45 %, dentro de 2 errores típicos) · BTC 4 h: n efectiva 4,2, no se lee.

**Tercera auditoría (2026-11-23):** n = 643 · E[R] −0,076 R (IC −0,124 … −0,028) · bruto +0,049 ·
costo 0,126 R · acierto 77,8 % frente a 83,9 % · PnL −2 585 USDT · 7 d: n = 233, E[R] −0,016 ·
funding 12 m BTC 3,435 % (sigue «cerca» del 4 %) · calidad HFT 0,972. Δ frente al 11-16: E[R] +0,034,
acierto +5,3 pts, PnL −33. **Ese «giro» no es medible** y la retroalimentación del 2026-11-23 lo dejó
escrito (`PLAN/notas/T210_utilidad_perfiles.md`): ΔE[R] W46 → W47 = +0,0485 ± 0,0845 (t = 1,12), la
diferencia mínima detectable entre dos semanas de ~230 operaciones es 0,121 R/op y lo observado pediría
≈ 12 semanas. Lo que mueve la utilidad es **cuántas operaciones tocan el tope completo** (29 de 233 en
W47 = −1 611 USDT frente a +1 490 de las otras 204), y los cuatro perfiles son **una apuesta con cuatro
tamaños** (587 de 643 operaciones cortas, 91 %), no cuatro muestras independientes.

**La puerta del marco mayor llega tarde y la rápida no informa (T212, 2026-11-23).** El lado del libro
lo fija `ProfileParams.htf` (15m → 1h EMA21/55, 1h → 4h EMA21/55, 4h → 4h EMA50/200) con el veto
`contra_tendencia`: 575 de 609 operaciones de BTCUSDT son cortas (94,4 %). Con el mínimo del 11-21 en
55 127 y el precio a +15,8 %, la puerta de 15m giró **35 h** tarde y las de 1h y 4h siguen bajistas tras
**758 y 718 h**; las aperturas posteriores al mínimo son 49, 45 cortas, **−731,7 USDT**. Antes de
proponer acelerarla: en los 95 días de velas de 1 h del disco la puerta rápida cambia **39 veces** y **no
distingue dirección** (retorno a 24 h: −0,338 % alcista frente a −0,158 % bajista), mientras las lentas sí
(+0,455 % y +0,234 %) — **ese «sí» de las lentas no se sostiene: T215 corrige el método, más
abajo**. Acortar las EMAs cambia sesgo por ruido, y tocar la puerta **reabre T139 P1**: es
◆ del usuario, nunca una propuesta de la auditoría. Detalle: el universo oficial incluye 38 operaciones
de ETHUSDT (+255,1 USDT) del 10-21 al 10-28, anteriores al foco T122.

**Cuarta auditoría (2026-11-26):** n = 726 · E[R] −0,074 R (IC −0,118 … −0,030) · bruto +0,051 ·
costo 0,125 R · acierto 78,1 % frente a 84,2 % · PnL −2 915 USDT · 7 d: n = 250, E[R] −0,040 ·
funding 12 m BTC 3,477 % (sigue «cerca» del 4 %) · calidad HFT 0,958. Δ frente al 11-23: E[R] +0,002,
PnL −330: dentro del ruido.

**El lado del libro, medido (T215, 2026-11-26).** Si se pregunta por el sesgo —«muchos cortos, pocos
largos»— la respuesta son estas tres cifras y no hace falta rehacerla: **652 de 726 operaciones son
cortas (89,8 %)**, con 15 días seguidos sin una sola larga (11-08 → 11-22) y 19/236 en los últimos
7 días; **dos de las tres puertas de T212 no han girado en 34 días** (1h bajista 821 h, 4h bajista
781 h), así que los marcos 1h y 4h solo pueden vender, mientras la rápida giró **tres veces en
cuatro días** y sus 18 largos del 11-23 perdieron −302,4 USDT. **Y el sesgo no es la fuga:** en la
sombra sin veto (11-19 → 11-25) el lado largo rinde −0,333 R (n = 420) frente a **+0,156** del corto
(n = 667), diferencia −0,490 ± 0,154 y −0,530 ± 0,204 agrupando por vela de apertura; en el libro
oficial queda dentro del ruido (−0,165 ± 0,299). Operar más largos habría perdido más. El costo del
retraso que midió T212 sigue en pie y es compatible: el sesgo cuesta **en los giros**. Cambiar la
puerta sigue siendo ◆ del usuario (T139 P1). Detalle: `PLAN/notas/T215_sesgo_direccional.md`.
**Desde T215 esto no se mide a mano:** la auditoría lo trae en el encabezado («LADO: …»), en la
línea «PUERTAS: …» y en la §6 del informe.

**Corrección a §5 de T212, medida al implementar T215:** el signo de una puerta **no** se juzga
promediando todas las velas de sus tramos (la ventana de las últimas cae al otro lado del giro, y
así 10 de 12 caminatas aleatorias puras aparentan señal). Medido **desde el giro**, en los 98 días
de velas del disco **ninguna** de las tres puertas distingue dirección: 15m +0,220 % con mínimo
detectable ±1,157 % (40 giros), 1h +1,973 % ± 6,206 % (3 giros) y 4h sin muestra (1 giro). Ya no
vale decir «las lentas sí distinguen»: era el mismo artefacto con el signo a favor, y la falta de
giros es justo lo que haría inmedible cualquier puerta alternativa (T139 P1).

**Quinta trampa, de T210: leer una diferencia semanal sin su diferencia mínima detectable.** Con la
varianza de la escalera (sd ≈ 0,46 R), una semana solo distingue ≈ 0,12 R/op: cualquier Δ menor que eso
se informa como «dentro del ruido» y no se convierte en hallazgo, ni al alza ni a la baja.

**Sexta trampa, de T215: contar el sesgo como si fuera la causa.** El desequilibrio es del veto, no de
las estrategias (la sombra genera 39 % de largos), y en una ventana en que el lado largo rinde peor,
«pocos largos» no explica la pérdida: el bruto es positivo y lo que la produce es el costo. El sesgo
se informa con su cifra y con el contraste de los dos lados agrupado por vela de apertura, nunca como
hallazgo por sí solo.

**Tres trampas que T175 quitó de la herramienta y que no hay que reintroducir a mano:**
comparar medias de dos mesas que toman ideas distintas (se empareja por perfil e idea); llevar al
usuario una estrategia porque su **neto** pierde (el costo solo ya lo produce: se juzga el bruto con
Holm entre las legibles); y dar por aplicada una palanca `auto` sin mirar el libro de la variante
(`auto_no_refleja_<marco>`). Y una cuarta: leer una calibración por su número de pronósticos y
no por su muestra efectiva (los horizontes se solapan: 105 pronósticos de 4 h son ≈ 4).

## 2. Procedimiento (5 pasos; no leas nada más salvo que un paso lo pida)

1. **Correr** (≈ 30 s, ligero, no hace falta la cola; la API tiene que estar en marcha):
   `python -m eim.analytics.audit` → lee **solo la salida de consola** (≈ 25 líneas). El informe
   completo queda en `reports/audit/audit_<fecha>.md` y el JSON al lado (es la referencia de la
   próxima vez). Sin API: `--ledger libro.csv`. Sin red: `--sin-red` (funding «sin medir»).
   En el equipo de la cantera, antes: `python -m eim.nursery report --sin-biblioteca` refresca
   `reports/nursery/latest.json`, que la auditoría lee en su §5 (T172). Esa lectura **no es una
   mirada** del escalafón: ascensos y bajas solo en las revisiones mensuales.
2. **Hitos de calendario** (comprueba la fecha de hoy contra esta lista; actualízala al cerrarse uno):
   - 2026-11-17 → T128 cerrada: la base de líderes crece ≈ +53 MB/día (antes ≈ +90); lo que falta es T178.
   - 2026-11-27 → **cierre de T31**: informe final, `risk_includes_costs` y freno gradual, ◆ sobre la variante t143.
   - 2026-12-06 → T135: veredicto del A/B de M8 (`reports/t135_ab/`), sin revisar antes.
   - 2026-12-17 03:25 UTC → **primera revisión de la cantera** (día 30 de `cantera_v1`); el
     informe de T172 sale solo al día siguiente (`reports/nursery/`). Siguientes: días 61, 91,
     121, 152 y **182 = 2027-05-18, cierre de la fase** (◆ de graduaciones, aunque no haya ninguna).
   - T78: cumplida al cerrar la hora 2026-11-14T07 UTC (72 h seguidas desde la 11T08); el cierre en `PLAN/STATUS.md` va con su gate.
   - 2027-05-06 → fecha límite de T139. 2027-10 → disparador A de T145.
3. **Clasificar cada oportunidad por su vía** (columna «vía» del informe):
   - `auto` → ya se adapta sola; solo comprueba que la variante t143 lo refleja.
   - `variante` → se puede proponer como corrida aparte (`EIM_PAPER_VARIANTS`), nunca en la oficial.
   - `◆` → pregunta al usuario, con la cifra y la vía; no la implementes.
   - `cerrada` → se informa en una línea, sin proponer nada.
   - `esperar` → anota cuánto falta (p. ej. n de la variante).
4. **Profundizar solo si** hay una oportunidad nueva, un disparador nuevo o «cerca», o el E[R] de
   los últimos 7 días sale del IC de la línea base. Dónde mirar, y nada más:
   - costo → `eim/paper/cost_ledger.py`, `reports/t143_maker.md`, `/v2/paper/variant/t143`
   - riesgo → `reports/t136_riesgo.md`, `eim/paper/risk_budget.py`
   - calibración → `/v2/calibration?symbol=BTCUSDT&tf=1h`, `reports/t150_calibracion.md`, `PLAN/T160.md`
   - catálogo → `PLAN/T49.md` (la puerta) antes de sugerir retirar una estrategia; Holm cuenta.
     La palanca ya filtra por bruto con Holm (T175): `estrategias_por_costo` es informativa
   - datos HFT → `python -m eim.operation.usage incidents --days 7` (T141/T148)
   - disparador de funding → `reports/arbitrage_edge.md` y BACKLOG T145 (3): pre-registro propio, sin la tenencia de 2 160 h
5. **Cerrar** (en un worktree propio si hay que escribir en `PLAN/`, nunca en la carpeta principal):
   - una entrada corta al final de `PLAN/BITACORA.md` (fecha, 3 cifras clave con su Δ, hallazgos, ◆);
   - cada hallazgo accionable → una tarea `PLAN/Txx.md` de la fase 25 o una línea en `PLAN/BACKLOG.md`
     bajo T159 (regla del usuario: los diagnósticos acaban en el plan, no en una lista suelta);
   - si algo cambió en §0 o §1 de esta skill, actualízala en el mismo PR.

## 3. Presupuesto de tokens

- No leas `ESTADO_PROYECTO.md`, `BITACORA.md` ni `STATUS.md` enteros: esta skill ya resume lo necesario.
- No abras el `.md` del informe salvo para la sección que necesites (`Grep` por el título).
- No relances backtests, bancos ni el gate para auditar. Si un hallazgo los pide, eso es una tarea.
- Un hallazgo sin cifra del informe no se escribe.

## 4. Mantener la herramienta

Las reglas viven en `eim/analytics/audit/levers.py` (umbrales arriba del archivo) y las cifras en
`kpis.py`. Una palanca nueva = una función con su vía, su referencia y su prueba en
`tests/analytics/test_audit.py`. Si cambia una decisión de §0, cambia también la vía en `levers.py`.
