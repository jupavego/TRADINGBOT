# Especificación de interfaz (decisiones del usuario; no cambiar sin consultar)

**Estilo:** limpio, amplio, dinámico e integral. Tema **futurista** por defecto (HUD neón: fondo azul noche, paneles de vidrio, acentos cian; verde = compra, rojo = venta, gris = neutral); temas oscuro y claro/cálido (como el panel F7) disponibles con el interruptor Tema. Tipografía sobria, mucho espacio, bordes finos, sin adornos. Por defecto se ven pocas capas; el resto se activa con un clic (divulgación progresiva).

**Layout "Mesa de trading":**
- Barra superior: activo, marco temporal, estado "En vivo" (punto), etiqueta de **modo** (Análisis/Simulado/Testnet) siempre visible.
- Centro (≈70 %): gráfico de velas en tiempo real (TradingView Lightweight Charts).
- Derecha: columna de agentes (tarjeta por agente: sesgo, confianza, estado, evidencia) y panel de síntesis.
- Abajo: panel con pestañas: Escenarios · Plan · Bitácora.
- Fila de capas activables: Canal, Niveles, Plan, Escenarios (activas por defecto); VWAP, Liquidaciones, Elliott, etc. (apagadas).

**El agente dibuja sobre el gráfico (en tiempo real, al cierre de cada vela; el precio actual se refresca por tick):**
- Soportes/resistencias como **zonas con grosor** (no líneas finas); canal o rango extendido hacia adelante.
- Plan: entrada, stop loss, take profit 1 y 2, relación riesgo/beneficio. Marcas de entradas/salidas pasadas. Al pasar el ratón sobre cualquier objeto: por qué existe (evidencia del agente).
- Deslizador de tiempo para reproducir decisiones pasadas.

**Escenarios (vista por defecto: trayectorias):** 3 (alcista/neutral/bajista) desde el precio actual, 20–30 velas, cada uno con trayectoria mediana + banda de incertidumbre + probabilidad (suman 100 %) + condición de invalidación. Colores: verde / azul / rojo con relleno suave. Interruptor opcional "Ver escenario como velas": muestra la secuencia OHLC simulada del escenario elegido (cuerpo lleno = sube, hueco = baja), etiquetada "simulada".

**Honestidad visible:** modo siempre rotulado; velas/trayectorias proyectadas rotuladas como simuladas; si el modelo no supera la línea base, la UI lo dice; cobertura y fuente de datos accesibles en cada panel.

**Técnico:** Vite + TypeScript, Lightweight Charts, WebSocket. Responsivo hasta tablet. Verificar con screenshot y leyendo los datos renderizados.
