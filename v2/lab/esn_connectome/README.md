# Laboratorio T28 — ESN con reservorio del conectoma de Drosophila

Fuera del paquete `eim/`: nada de aquí se importa desde producción. Informe: `v2/reports/esn_connectome.md`.

## Datos
- Velas 1h BTCUSDT/ETHUSDT del almacén local (`v2/data`, Binance, 2023-01 → 2026-10).
- Conectoma: FlyWire v783, `proofread_connections_783.feather` (Zenodo 10.5281/zenodo.10676866,
  **CC BY 4.0**: atribución a FlyWire Consortium; Dorkenwald et al. 2024 y Schlegel et al. 2024, *Nature*).
  El archivo de 852 MB no se versiona; `data/subgraph_1000.npz` (subgrafo derivado, 1.000 neuronas) sí,
  con la misma licencia y atribución.

## Modelos (todos predicen cuantiles del retorno log a h = 25 velas)
| nombre | descripción |
|---|---|
| `cone` | cono de volatilidad: cuantiles empíricos de `R/(σ√h)` en entrenamiento × σ actual (EWMA) |
| `base_T16` | motor base de `eim/forecast` (GARCH(1,1) + bootstrap de formas, 200 trayectorias) |
| `linear` | misma lectura de cuantiles que los ESN, sobre 24 rezagos de las entradas (sin reservorio) |
| `esn_random` | reservorio Erdős–Rényi con la densidad del subgrafo, pesos gaussianos |
| `esn_connectome` | topología y pesos reales: `sign(nt)·log(1+sinapsis)` |
| `esn_topology` | topología real con pesos gaussianos |

Kronos **no** se evalúa (sin torch instalado; decisión del usuario 2026-10-13). Si el ESN no supera al
cono, Kronos no cambia el veredicto.

## Protocolo
Pliegues: 1 año de entrenamiento → 6 meses de prueba, rodando 6 meses (6 por activo). Orígenes de prueba cada
25 velas (sin solapamiento). ρ ∈ {0.5, 0.9, 1.2}, fuga ∈ {0.1, 0.5} y alpha de ridge se eligen por pliegue en
validación interna (último 25 % del entrenamiento, hueco h). Misma `W_in` por semilla en las tres variantes.
Costos (dirección): ida y vuelta 12 pb (taker 5 pb + deslizamiento 1 pb por lado, como T25); posición =
signo de la mediana pronosticada.

## Criterios (fijados ANTES de correr con el conectoma real)
- **C1** `esn_connectome` gana a `esn_random` en pinball en ≥ 75 % de las celdas activo×pliegue
  (media de semillas) **y** el IC95 % bootstrap de la diferencia media por origen es < 0.
- **C2** igual que C1 frente a `cone` **y** frente a `base_T16`.
- **C3** cobertura 80 % ∈ [75 %, 85 %] y 50 % ∈ [45 %, 55 %].
- **C4** (económico, informativo) acierto direccional > 50 % con p de Holm < 0.05 y PnL neto por operación
  con IC95 % > 0.

**Veredicto «gana» solo si C1 ∧ C2 ∧ C3.** Entonces (y solo entonces) se envuelve como `Engine` opcional;
C4 decide si sirve para operar. Si no, se archiva sin tocar el resto.

## Reproducir (desde `v2/`)
```
pip install pyarrow   # solo para extraer el subgrafo
python -m lab.esn_connectome.connectome --src C:/t28data/proofread_connections_783.feather
python -m lab.esn_connectome.run_lab --n 500 --seeds 5 --out reports/esn_connectome/n500.json
python -m lab.esn_connectome.summarize reports/esn_connectome/n500.json
```
