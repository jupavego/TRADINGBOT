# T100 · sonda sobre datos reales (renta fija)

Calculado 2026-11-26T23:00:47+00:00 · modo ANÁLISIS · fuente de la curva: Tesoro de EE. UU. (curva par diaria, reutilización declarada sin restricción).

## Curva del 2026-11-25 (475 días descargados)

- 10 años 4.85 % · 2 años 4.61 % · 3 meses 4.34 %
- pendiente 3m10a +51 pb · 2s10s +24 pb · curvatura +3 pb
- Svensson reproduce la curva con 1.5 pb de error medio (Nelson–Siegel: 7.5 pb)
- ⚠ τ de Svensson en el borde de la rejilla: sus β no se interpretan (solo sirven para interpolar)

## Carry + roll-down a 3 meses con la curva quieta

| Plazo | Carry | Roll-down | Financiación | Exceso | Vol. rend. | Exceso/riesgo | Punto muerto |
|---|---|---|---|---|---|---|---|
| 2a | +114 pb | +2 pb | 107 pb | +9 pb | 50 pb | +0.10 | 5 pb |
| 5a | +115 pb | +1 pb | 107 pb | +8 pb | 50 pb | +0.04 | 2 pb |
| 10a | +121 pb | +10 pb | 107 pb | +24 pb | 45 pb | +0.05 | 2 pb |
| 30a | +132 pb | -10 pb | 107 pb | +15 pb | 38 pb | +0.01 | 0 pb |

Financiación aproximada por la letra de 3 meses (no repo/SOFR). Prototipo sin validar: no es una señal ni vota.

## Contraste de la fórmula de Svensson con el BCE

**coincide** (día 2026-11-25; diferencia máxima 0.0 pb, tolerancia 0.5 pb). Fuente: Banco Central Europeo.

| Plazo | BCE % | EIM % | Dif. pb |
|---|---|---|---|
| 1 | 2.9238717697 | 2.923872 | -0.0 |
| 2 | 2.9686993028 | 2.968699 | 0.0 |
| 5 | 2.9925799666 | 2.99258 | 0.0 |
| 10 | 3.2591807487 | 3.259181 | 0.0 |
| 30 | 3.5764528468 | 3.576453 | 0.0 |
