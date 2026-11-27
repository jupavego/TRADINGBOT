# T209 — Recuento retro de los vetos por datos de la corrida de operación

Fuente: `v2/data/operation/logs/op-2026-1*.jsonl` de `juanpablo-cpu` (eventos `decision` con plan,
del 2026-10-19 al 2026-11-23 ≈ 02:00 UTC). Medido el 2026-11-23.

## Cómo se cuenta
- **Decisión:** un evento `decision` con plan, sin repetir el mismo plan dentro del mismo minuto (el
  registro escribe cada decisión dos veces: `decision` y dentro de `ciclo`).
- **Plan:** un mismo plan se vuelve a decidir mientras sigue vigente, sobre todo tras cada reinicio
  de la API. Por plan se toma su **primera** decisión.
- **Con T209:** `literature` y `vwap` dejan de degradarse por la ventana. En 1h con 500 velas, esas
  eran **todas** sus degradaciones: `literature` solo se degradaba por fichas que no cabían y `vwap`
  solo por períodos parciales. Así que, para la regla de datos, el recuento sin ellos es exacto. Lo
  que no se puede rehacer es la síntesis: con `vwap` votando entero a fin de mes, algún plan habría
  salido distinto o no habría salido.

## Por decisión
| Semana | Decisiones | Aprobadas | Vetadas por datos | Pasarían datos | Sin otro veto |
|---|--:|--:|--:|--:|--:|
| W43 | 10 | 5 | 1 | 1 | 0 |
| W44 | 15 | 1 | 14 | 4 | 3 |
| W45 | 29 | 0 | 29 | 15 | 9 |
| W46 | 8 | 1 | 7 | 5 | 0 |
| W47 | 8 | 0 | 8 | 8 | 8 |
| **Total** | **70** | **7** | **59** | **33** | **20** |

## Por plan (primera decisión de cada uno)
**34 planes distintos**, 6 con alguna decisión aprobada. **26 se vetaron por datos** en su primera
decisión; con T209, **12 habrían pasado** el filtro de datos y **5** no tenían ningún otro veto.

## Lo que sigue vetado, y está bien
- 25 decisiones por `liquidations` + `microstructure` y 1 por `calendar` + `liquidations`: son
  datos que fallan (huecos de secuencia en la captura HFT por encima del 30 %, el dataset de
  liquidaciones obsoleto o sin cobertura, un problema del calendario). La regla debe seguir
  vetándolas; `tests/agents/test_window_t209.py::test_two_real_degradations_still_veto` lo fija.
- De las 33 que pasarían el filtro de datos, 13 tenían otro veto: «operaciones abiertas» (12) y
  «vigencia» (3); algunas tenían los dos.

## Lectura
La corrida de T31 no estaba midiendo la estrategia sino una regla de datos mal alimentada: en W45 no
se aprobó ninguna de 29 decisiones y en W47 ninguna de 8, y en las dos semanas el motivo común era
`literature`. El arreglo devuelve a la corrida las decisiones que solo vetaba la ventana. Con lo que
hay no se puede decir si esas operaciones habrían ganado.
