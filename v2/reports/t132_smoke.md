# T132 — las candidatas sobre la copia real (BTCUSDT)

**Modo: SIMULADO.** Generado el 2026-11-04T00:14+00:00 desde `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` (commit `6b78951`), σ `parkinson`, marco mayor `1h`, 2019972 velas de 1 min. 4000 ideas, 2860 emparejadas, 189 s.

**Esto no elige ninguna política ni ajusta parámetros: eso es T134.** Solo comprueba que corren sobre datos reales y con qué cobertura de rasgos.

## Cobertura de los rasgos

| Estimador σ | σ | swing bajo | swing alto | marco mayor | rango |
|---|--:|--:|--:|--:|--:|
| `atr14` | 100.0% | 100.0% | 100.0% | 100.0% | 99.9% |
| `parkinson` | 99.9% | 100.0% | 100.0% | 100.0% | 99.9% |
| `garman_klass` | 99.9% | 100.0% | 100.0% | 100.0% | 99.9% |
| `yang_zhang` | 99.9% | 100.0% | 100.0% | 100.0% | 99.9% |
| `harrv_1m` | 94.8% | 100.0% | 100.0% | 100.0% | 99.9% |

Un rasgo con poca cobertura no es un error: la política que lo use se queda con su valor base en esas velas, que es la regla del proyecto (la falta de datos no aprieta). Pero hay que saberlo antes de medir.

## Las candidatas corren

| Política | n | Acierto | E[R] | PF | Costo R | Motivos de cierre |
|---|--:|--:|--:|--:|--:|---|
| `M2 k=3` | 2995 | 45.4% | -0.110 | +0.74 | +0.186 | {'SL': 936, 'SLD': 2059} |
| `M3 f5` | 2995 | 27.9% | -0.024 | +0.94 | +0.169 | {'SL': 278, 'SLD': 2717} |
| `M5` | 2995 | 50.7% | -0.107 | +0.81 | +0.200 | {'SL': 1411, 'SLD': 1584} |
| `M6 b16` | 2890 | 6.9% | -0.923 | +0.01 | +0.222 | {'SL': 1878, 'TIEMPO': 1012} |
| `M7` | 2995 | 25.2% | +0.156 | +1.18 | +0.206 | {'HTF': 970, 'SL': 2025} |
| `S1 d2 + M2` | 2995 | 31.3% | -0.103 | +0.70 | +0.174 | {'SL': 75, 'SLD': 2920} |
| `S1 d2 sola` | 2860 | 0.1% | -1.257 | +0.00 | +0.257 | {'SL': 2860} |

Las cifras son descriptivas y de un tramo recortado: **no** son fuera de muestra ni pasan por los criterios de §5.4.

