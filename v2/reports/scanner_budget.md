# Presupuesto del escáner global (T93)

Universo: perpetuos USDⓈ-M de Binance liquidados en USDT (catálogo de T89, almacén de T181). Marco `1d`, `asof` = 1795651200000 (la última vela guardada: el barrido es reproducible). Modo ANÁLISIS: el escáner no envía órdenes.

## Barrido completo (en frío)

| Medida | Valor |
|---|---:|
| Instrumentos en el catálogo (plaza) | 958 |
| Pasan la etapa 1 (descubrimiento) | 764 |
| Pasan la etapa 2 (datos) y se puntúan | 564 |
| Lista corta a la cola (ritmo profundo) | 25 |
| Catálogo · etapa 1 · lectura · etapa 2 · etapa 3 (s) | 0.138 · 0.003 · 0.947 · 0.029 · 0.012 |
| Embudo completo (etapas 1–3, s) | 1.129 |
| Instrumentos con datos por segundo | 676.9 |
| **ms por instrumento con datos** (etapa 2; presupuesto T87: 20) | **1.477** — dentro |
| Etapa 3 sola (ms por instrumento puntuado) | 0.01538 |
| Preparación profunda de la lista corta (2 proceso(s), s) | 1.641 |
| Persistencia en `scanner.duckdb` (s) | 2.974 |
| Pico de memoria Python/NumPy (MB) | 22.9 |
| Pico de memoria del proceso (MB) | no medido |
| Panel en memoria (MB) | 3.15 |

Exclusiones por motivo: `estado` 141, `liquidez` 152, `moneda` 46, `no_perpetuo` 4, `pocas_velas` 48, `pre_opv` 3.

## Reproducibilidad y caché (segundo barrido, mismas entradas)

- Huella de puntuaciones: `9e34ec13cafb19718beff634` → `9e34ec13cafb19718beff634` (idénticas).
- Acierto de caché de la cola: en frío 0 %, en caliente 100 % (clave: instrumento, marco, hash de datos, versión).
- Embudo en caliente: 1.188 s; preparación profunda 0.340 s.

## Proyección

| Instrumentos | Etapa 3 (s, medida) | Estadísticas (s, medida) | Lectura+filtros (s, proyectada) | Total (s) | ms/instrumento | Panel (MB) |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.0118 | 0.0051 | 1.423 | 1.44 | 1.4403 | 4.13 |
| 10,000 | 0.1119 | 0.0792 | 14.234 | 14.425 | 1.4425 | 41.28 |

La etapa 3 se mide en paneles sintéticos (paseo aleatorio con semilla); la lectura del almacén se proyecta lineal desde el universo real. Reproducible con `python -m eim.scanner budget` desde `v2/`.
