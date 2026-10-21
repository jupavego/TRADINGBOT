# Topes de riesgo de los perfiles (evidencia en sombra)

Ventana: 3–21 oct 2026 (~18 días), BTCUSDT y ETHUSDT, contextos y velas locales, mismas ideas en
todas las variantes. **Los umbrales se eligieron mirando estos datos**: confirmar con la corrida en
vivo. Muestras pequeñas (20–60 operaciones por variante).

Diagnóstico: expectativa ≈ −0,5 R/op en BTC con acierto ≈ 38 % (un TP gana +0,85 R, un SL cuesta
−1,15 R); el Agresivo (2 % de riesgo, 10x, hasta 10 posiciones) multiplica esa pérdida y concentra
hasta 9 posiciones largas correlacionadas que fallan juntas.

| BTCUSDT | Capital | Ret. | DD máx. | Ops | Acierto |
|---|---|---|---|---|---|
| Agresivo base | 4.822 | −51,8 % | 54,0 % | 106 | 39 % |
| Agresivo tope 3 % + freno 5 % (**adoptado**) | 8.621 | −13,8 % | 19,6 % | 48 | 52 % |
| Moderado base | 8.857 | −11,4 % | 13,9 % | 66 | 38 % |
| Moderado tope 3 % + freno 5 % (**adoptado**) | 9.044 | −9,6 % | 12,0 % | 59 | 39 % |

ETHUSDT: Moderado sin cambio (+6,0 %); Agresivo +12,3 % → +8,9 % con DD 14,7 % → 3,8 %.

## Palancas descartadas o no adoptadas
- **Filtro de régimen «sin rango»**: en BTC el 90 % de todo (ganador o perdedor) ocurre en «rango»; quitarlo
  deja 14–19 operaciones (casi dejar de operar) y en ETH baja el retorno. No discrimina: no se implementa.
- **Sin peso en observación / `n_min` 15**: mejoran el Moderado pero empeoran el Agresivo sin tope
  (−33 %) y son inconsistentes entre BTC y ETH.
- **Bajar apalancamiento o `max_open`**: reducen la pérdida solo por escala; el tope por dirección lo
  logra con menos pérdida de ganancia en ETH.
- **Freno por drawdown solo**: inconsistente (en ETH con 5 % pasa de +10 % a −10 %).
