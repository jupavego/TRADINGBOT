# T170 — Examen físico de las dos reglas rediseñadas

**Modo: SIMULADO.** Sin rendimiento: ni R neto, ni acierto, ni PF. Misma ficha que T169 (`PLAN/T169.md`, banda medida) y mismos contextos guardados de 1 h (10752 en 16 tramos de 28 días, 448,0 días).

| Prospecto | Banda | Ideas | Operaciones | No llenadas | Al mes | Costo medio (R) | Tenencia mediana (h) | En posición (días) | Estado |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| `estructura_ruptura` | scalping (declarada intradia) | 505 | 382 | 6 | 25,6 | 0,153 | 1,2 | 47% | sigue |
| `tec_acuerdo_marcos` | scalping (declarada tres_dias) | 2874 | 561 | 5 | 37,6 | 0,145 | 2,0 | 72% | sigue |

## Motivos y huellas

- `estructura_ruptura`: cumple la ficha. Huella T169 `1d4c4f294f59` → T170 `f732d941eeca`. Regla: Entra en el sentido del sesgo cuando el escenario pasa a SC-02, sin filtro de convicción. Rediseñada en T170: el umbral provisional de 60 (banda SR-2) no se cumplía nunca, porque el agente da a SC-02 una convicción de 47–50 (T169).
- `tec_acuerdo_marcos`: cumple la ficha. Huella T169 `61b1b609e29f` → T170 `a3e0ee4321f2`. Regla: Largo si el sesgo de 1 h y el de 4 h superan +mtf_neutral; corto en espejo. Sale cuando un marco deja de estar de acuerdo. Rediseñada en T170: con base 1 h el agente solo evalúa sus marcos vecinos, así que el de 1 d no existía nunca (T169).

## No anticipación

Heredada de T169: 54 contextos de 1 h recalculados con el banco truncado, 0 distintos. Las dos reglas son funciones puras de esos contextos, así que sus ideas no pueden cambiar al truncar.
