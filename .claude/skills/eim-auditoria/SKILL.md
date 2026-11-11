---
name: eim-auditoria
description: Auditoría periódica de rentabilidad, riesgo y calibración del EIM (T159, fase 25) con poco gasto de tokens. Úsala cuando se pida «auditoría», «revisión periódica», «calibración», «cómo vamos», «oportunidades de mejora/rentabilidad», al cerrar una semana de T31, o cuando la tarea programada de auditoría la lance.
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
| Multiplicidad | Todo intento cuenta en Holm (familia 841) | T49, T139 |
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

## 2. Procedimiento (5 pasos; no leas nada más salvo que un paso lo pida)

1. **Correr** (≈ 30 s, ligero, no hace falta la cola; la API tiene que estar en marcha):
   `python -m eim.analytics.audit` → lee **solo la salida de consola** (≈ 25 líneas). El informe
   completo queda en `reports/audit/audit_<fecha>.md` y el JSON al lado (es la referencia de la
   próxima vez). Sin API: `--ledger libro.csv`. Sin red: `--sin-red` (funding «sin medir»).
2. **Hitos de calendario** (comprueba la fecha de hoy contra esta lista; actualízala al cerrarse uno):
   - 2026-11-17 → T128: medición de la base de líderes cumplida, cerrar T128.
   - 2026-11-27 → **cierre de T31**: informe final, `risk_includes_costs` y freno gradual, ◆ sobre la variante t143.
   - 2026-12-06 → T135: veredicto del A/B de M8 (`reports/t135_ab/`), sin revisar antes.
   - T78: se cumple cuando la racha llegue a 72 h (`python -m eim.data.collectors.hft_ops --root data --streak`).
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
   - calibración → `/v2/calibration?symbol=BTCUSDT&tf=1h`, `reports/t150_calibracion.md`
   - catálogo → `PLAN/T49.md` (la puerta) antes de sugerir retirar una estrategia; Holm cuenta
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
