### N = 500 neuronas · 5 semillas · h = 25 · costo i/v 12 pb
Subgrafo: 32487 aristas (densidad 13.0%), 48% presinápticas inhibidoras, 46% aristas recíprocas.

| modelo | pinball (×1e4) | cob50 | cob80 | acierto dir. | p Holm | neto/op (pb) | IC95 neto |
|---|---|---|---|---|---|---|---|
| cone | 66.48 | 49.3% | 79.8% | 51.4% | — | -20.2 | [-33.9, -6.7] |
| base_T16 | 66.57 | 56.3% | 82.7% | 48.3% | — | -22.1 | [-35.9, -8.8] |
| linear | 65.92 | 49.4% | 79.1% | 51.2% | 0.619 | -5.5 | [-18.2, +7.9] |
| esn_random | 66.04 | 48.7% | 78.6% | 50.8% | 0.769 | -9.6 | [-15.5, -3.9] |
| esn_connectome | 66.04 | 48.6% | 78.9% | 50.6% | 0.769 | -13.4 | [-19.3, -7.7] |
| esn_topology | 66.07 | 48.6% | 78.7% | 50.3% | 0.769 | -14.2 | [-20.1, -8.4] |

| comparación (pinball) | celdas ganadas | dif. media (×1e4) | IC95 | skill |
|---|---|---|---|---|
| esn_connectome vs esn_random | 50% de 12 | -0.004 | [-0.165, +0.148] | +0.01% |
| esn_connectome vs cone | 75% de 12 | -0.446 | [-1.034, +0.149] | +0.67% |
| esn_connectome vs base_T16 | 75% de 12 | -0.537 | [-1.167, +0.094] | +0.81% |
| esn_connectome vs linear | 42% de 12 | +0.116 | [-0.281, +0.511] | -0.18% |
| esn_topology vs esn_random | 42% de 12 | +0.026 | [-0.119, +0.158] | -0.04% |
| esn_connectome vs esn_topology | 67% de 12 | -0.030 | [-0.178, +0.122] | +0.05% |
| esn_random vs cone | 75% de 12 | -0.443 | [-1.031, +0.163] | +0.67% |
| linear vs cone | 75% de 12 | -0.562 | [-1.144, +0.018] | +0.85% |
| base_T16 vs cone | 50% de 12 | +0.090 | [-0.298, +0.457] | -0.14% |

Criterios: C1 no · C2 no · C3 sí · C4 no → **NO GANA**

### N = 100 neuronas · 3 semillas · h = 25 · costo i/v 12 pb
Subgrafo: 1739 aristas (densidad 17.4%), 53% presinápticas inhibidoras, 71% aristas recíprocas.

| modelo | pinball (×1e4) | cob50 | cob80 | acierto dir. | p Holm | neto/op (pb) | IC95 neto |
|---|---|---|---|---|---|---|---|
| cone | 66.48 | 49.3% | 79.8% | 51.4% | — | -20.2 | [-33.9, -6.7] |
| base_T16 | 66.57 | 56.3% | 82.7% | 48.3% | — | -22.1 | [-35.9, -8.8] |
| linear | 65.92 | 49.4% | 79.1% | 51.2% | 0.428 | -5.5 | [-18.2, +7.9] |
| esn_random | 66.00 | 49.0% | 79.0% | 51.0% | 0.428 | -12.7 | [-20.2, -4.8] |
| esn_connectome | 65.85 | 48.6% | 79.3% | 51.4% | 0.428 | -13.1 | [-21.0, -5.5] |
| esn_topology | 65.77 | 48.7% | 79.3% | 51.4% | 0.428 | -11.3 | [-19.2, -3.7] |

| comparación (pinball) | celdas ganadas | dif. media (×1e4) | IC95 | skill |
|---|---|---|---|---|
| esn_connectome vs esn_random | 58% de 12 | -0.146 | [-0.349, +0.052] | +0.22% |
| esn_connectome vs cone | 83% de 12 | -0.632 | [-1.199, -0.069] | +0.95% |
| esn_connectome vs base_T16 | 83% de 12 | -0.722 | [-1.336, -0.102] | +1.08% |
| esn_connectome vs linear | 58% de 12 | -0.069 | [-0.497, +0.351] | +0.11% |
| esn_topology vs esn_random | 58% de 12 | -0.231 | [-0.417, -0.047] | +0.35% |
| esn_connectome vs esn_topology | 83% de 12 | +0.085 | [-0.134, +0.295] | -0.13% |
| esn_random vs cone | 75% de 12 | -0.486 | [-1.051, +0.076] | +0.73% |
| linear vs cone | 75% de 12 | -0.562 | [-1.144, +0.018] | +0.85% |
| base_T16 vs cone | 50% de 12 | +0.090 | [-0.298, +0.457] | -0.14% |

Criterios: C1 no · C2 sí · C3 sí · C4 no → **NO GANA**

### N = 1000 neuronas · 3 semillas · h = 25 · costo i/v 12 pb
Subgrafo: 94397 aristas (densidad 9.4%), 46% presinápticas inhibidoras, 42% aristas recíprocas.

| modelo | pinball (×1e4) | cob50 | cob80 | acierto dir. | p Holm | neto/op (pb) | IC95 neto |
|---|---|---|---|---|---|---|---|
| cone | 66.48 | 49.3% | 79.8% | 51.4% | — | -20.2 | [-33.9, -6.7] |
| base_T16 | 66.57 | 56.3% | 82.7% | 48.3% | — | -22.1 | [-35.9, -8.8] |
| linear | 65.92 | 49.4% | 79.1% | 51.2% | 0.619 | -5.5 | [-18.2, +7.9] |
| esn_random | 65.86 | 49.0% | 78.6% | 50.5% | 1.000 | -14.0 | [-21.9, -6.3] |
| esn_connectome | 65.82 | 48.3% | 78.9% | 50.3% | 1.000 | -18.6 | [-26.0, -11.0] |
| esn_topology | 65.91 | 48.5% | 78.5% | 50.3% | 1.000 | -15.4 | [-22.8, -7.8] |

| comparación (pinball) | celdas ganadas | dif. media (×1e4) | IC95 | skill |
|---|---|---|---|---|
| esn_connectome vs esn_random | 58% de 12 | -0.033 | [-0.294, +0.231] | +0.05% |
| esn_connectome vs cone | 75% de 12 | -0.661 | [-1.220, -0.102] | +0.99% |
| esn_connectome vs base_T16 | 75% de 12 | -0.751 | [-1.354, -0.142] | +1.13% |
| esn_connectome vs linear | 50% de 12 | -0.099 | [-0.561, +0.352] | +0.15% |
| esn_topology vs esn_random | 58% de 12 | +0.049 | [-0.113, +0.227] | -0.07% |
| esn_connectome vs esn_topology | 42% de 12 | -0.082 | [-0.403, +0.207] | +0.12% |
| esn_random vs cone | 83% de 12 | -0.627 | [-1.163, -0.092] | +0.94% |
| linear vs cone | 75% de 12 | -0.562 | [-1.144, +0.018] | +0.85% |
| base_T16 vs cone | 50% de 12 | +0.090 | [-0.298, +0.457] | -0.14% |

Criterios: C1 no · C2 sí · C3 sí · C4 no → **NO GANA**

