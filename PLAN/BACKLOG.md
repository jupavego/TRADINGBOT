# Backlog (una línea por ítem; lo que quedó fuera del alcance de una tarea)

- [T02] CONVICTION_SCORE (24 filas) y CONFIDENCE_SCORE (13 filas) del CSV histórico difieren de lo que F7 calcula hoy (el CSV es de una corrida previa a correcciones de BRM/IRM); el golden congela el comportamiento ACTUAL de F7. Verificar en T05 que es el deseado.
- T03: `BinanceFutures.open_interest` devuelve solo las últimas ~500 filas si la ventana de 29 días supera el límite de página (Binance entrega el tramo más reciente); paginar hacia atrás para cubrir toda la ventana.
- T03: `sync_derivatives` / funding no cubre `XAUUSDT` ni yfinance (fuera de alcance); sin CLI de sincronización (hoy se usa desde código).
- [T07] Legado F7 `EIMSeasonality`: `pct_change` calcula el retorno entre filas aunque falte un mes (el comentario dice NaN pero no lo hace); v2 usa `strict_gaps=True` por defecto, el golden se reproduce con `strict_gaps=False`.
- [T07] `build_snapshot` (data/snapshot.py) aún no rellena `snapshot.liquidations` ni hay cierres mensuales de 1M propios; conectar `BinanceLiquidations.fetch` al almacén/API en T08. El agente `seasonality` necesita historia mensual larga (velas 1d/1M) en el snapshot.
- [T09] La API emite `status up` al abrir el WS aunque la fuente no entregue ticks (en esta red `fstream.binance.com` conecta pero no envía; el spot `wss://stream.binance.com:9443/ws` sí vía `EIM_WS_URL`). Añadir detección de feed silencioso (sin ticks en N s → estado `stale`) y mostrar "Datos detenidos" en la UI.
- [T09] Vite 8 exige Node ≥20.19; se fijó Vite 5 por Node 20.18. Reevaluar al actualizar Node.

- T11: Liquidaciones sin mapa de calor precio×tiempo (solo totales diarios y niveles); `/v2/more/*` sin caché del backtest; pestañas legadas Histórico/Variables crudas/Price Action/Elliott ya cubiertas por agentes, sin vista dedicada.
- [Fase 8] Arbitraje entre exchanges y con DEX (fuera del alcance «solo Binance»); estrategias de alta frecuencia; copy trading de perfiles Binance si T33 no lo permite (reevaluar vía API oficial si Binance la publica).
- Techo/piso por escenario: hecho con Fibonacci + proyección de onda tipo Elliott (zigzag) + pivotes + envolvente estadística. Pendiente: usar el conteo de ondas del agente `elliott` (en vez de zigzag propio), zonas de `levels` con toques/volumen, confluencia ponderada y evaluar en calibración si techo/piso se respetan.
