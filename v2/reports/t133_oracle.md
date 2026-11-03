# T133 · entregable 0 — cota del oráculo de M4 (BTCUSDT)

**Modo: SIMULADO.** Pre-registro `prereg_t131_v2`, huella `0dd3d9d8550beac0…`. Generado el 2026-11-03T23:08+00:00 desde la copia `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` (commit `28d46ea`), 2019972 velas de 1 min.

Ventana **2023-01-11T10:00+00:00 → 2026-08-16T00:00+00:00**, 10 pliegues, embargo 200 h. 60720 ideas, 45822 emparejadas; las cifras son de los tramos de **prueba** (purga y embargo de T131 incluidos).

## Veredicto

> M4 SE DESCARTA (E6): ni conociendo el régimen con certeza cumpliría los criterios 1–3 de §5.4 — frente a M0 first_r=0.1 falla el criterio 2 (cociente y PF) y el 3 (DD y CVaR); frente a M1 be=1/0.1 falla el criterio 2 (cociente y PF). Un predictor real recupera solo una fracción de ese techo, así que no hay nada que recuperar y no se construyen rasgos

## Qué es cada cota

- **`M4_oraculo`** — la cota que pre-registra E6: con la etiqueta **ex post** del día se toma M0 en los días laterales y M1 en los de tendencia. Es información que no se conoce al entrar, así que marca el **techo de un selector de régimen perfecto**.
- **`M4_envolvente`** — contexto, no cota: en cada entrada toma la **mejor de las dos salidas** sabiendo ya cómo acabó. No es un selector de régimen (acierta operación a operación, no día a día), así que cumplir los criterios con ella **no prueba nada**; se publica para que se vea cuánta información futura hace falta para que estas entradas sean rentables.

Reparto de los días: {'Intermedio': 14466, 'Lateral': 13474, 'sin_dato': 42, 'Tendencia': 17840}.
Mapa declarado del oráculo: {'Lateral': 'M0', 'Tendencia': 'M1', 'Intermedio': 'M0', 'sin_dato': 'M0'}.
Veces que la envolvente eligió cada salida: {'M0 first_r=0.1': 28794, 'M1 be=1/0.1': 17028}.

## Cifras

| Serie | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | DD máx. R | CVaR 95 % |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M0 first_r=0.1` | 29828 | 76.1% | -0.1538 | +0.127 | -1.048 | +0.12 | +0.386 | +4591 | -1.3499 |
| `M1 be=1/0.1` | 29828 | 49.2% | -0.1525 | +0.843 | -1.115 | +0.76 | +0.731 | +4560 | -1.3943 |
| `M4_oraculo` | 29828 | 67.8% | -0.0932 | +0.386 | -1.101 | +0.35 | +0.737 | +2812 | -1.3731 |
| `M4_envolvente` | 29828 | 78.1% | +0.2100 | +0.586 | -1.131 | +0.52 | +1.848 | +45 | -1.3497 |

## Criterios 1–3 de §5.4

### `M4_oraculo`

| Base | ΔE[R] | IC 95 % | 1 (Δ e IC) | 2 (cociente y PF) | 3 (DD y CVaR) | ¿cumple 1–3? |
|---|--:|---|---|---|---|---|
| `M0 first_r=0.1` | +0.0606 | [+0.0453, +0.0758] | sí | **NO** | **NO** | **NO** |
| `M1 be=1/0.1` | +0.0592 | [+0.0461, +0.0728] | sí | **NO** | sí | **NO** |

- Frente a `M0 first_r=0.1`: cociente +0.35 (exige ≥ 0,50) · PF +0.737 (exige ≥ +0.444) · DD +2812 R (permite ≤ +5050) · CVaR -1.3731 (base -1.3499).
- Frente a `M1 be=1/0.1`: cociente +0.35 (exige ≥ 0,50) · PF +0.737 (exige ≥ +0.841) · DD +2812 R (permite ≤ +5016) · CVaR -1.3731 (base -1.3943).

### `M4_envolvente`

| Base | ΔE[R] | IC 95 % | 1 (Δ e IC) | 2 (cociente y PF) | 3 (DD y CVaR) | ¿cumple 1–3? |
|---|--:|---|---|---|---|---|
| `M0 first_r=0.1` | +0.3639 | [+0.3494, +0.3786] | sí | sí | sí | sí |
| `M1 be=1/0.1` | +0.3625 | [+0.3522, +0.3730] | sí | sí | sí | sí |

- Frente a `M0 first_r=0.1`: cociente +0.52 (exige ≥ 0,50) · PF +1.848 (exige ≥ +0.444) · DD +45 R (permite ≤ +5050) · CVaR -1.3497 (base -1.3499).
- Frente a `M1 be=1/0.1`: cociente +0.52 (exige ≥ 0,50) · PF +1.848 (exige ≥ +0.841) · DD +45 R (permite ≤ +5016) · CVaR -1.3497 (base -1.3943).

## Lo que esto NO dice

- No dice que el régimen sea impredecible: dice que **aunque se predijera perfecto**, elegir entre M0 y M1 por el régimen del día no alcanza los criterios de adopción.
- No afecta a M2, M3, M5, M8 ni S1: son salidas que cambian la **geometría** del stop, no un selector entre las dos de hoy. Eso es T132.
- No cambia nada en vivo: la escalera sigue siendo la salida vigente (◆1 de T129).

