# Backlog (una línea por ítem; lo que quedó fuera del alcance de una tarea)

- [T02] CONVICTION_SCORE (24 filas) y CONFIDENCE_SCORE (13 filas) del CSV histórico difieren de lo que F7 calcula hoy (el CSV es de una corrida previa a correcciones de BRM/IRM); el golden congela el comportamiento ACTUAL de F7. Verificar en T05 que es el deseado.
- T03: `BinanceFutures.open_interest` devuelve solo las últimas ~500 filas si la ventana de 29 días supera el límite de página (Binance entrega el tramo más reciente); paginar hacia atrás para cubrir toda la ventana.
- T03: `sync_derivatives` / funding no cubre `XAUUSDT` ni yfinance (fuera de alcance); sin CLI de sincronización (hoy se usa desde código).
