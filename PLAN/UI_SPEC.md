# Especificación de interfaz (decisiones del usuario; no cambiar sin consultar)

**Estilo:** limpio, amplio, dinámico e integral. Tema **futurista** como única apariencia (HUD neón: fondo azul noche, paneles de vidrio, acentos cian; verde = compra, rojo = venta, gris = neutral). Decisión del usuario 2026-10-22 (T122): se retiraron el interruptor Tema y los temas oscuro y claro, y la franja animada tipo radar que barría la pantalla. Tipografía sobria, mucho espacio, bordes finos, sin adornos. Por defecto se ven pocas capas; el resto se activa con un clic (divulgación progresiva).

**Layout "Mesa de trading":**
- Barra superior: activo, marco temporal, estado "En vivo" (punto), etiqueta de **modo** (Análisis/Simulado/Testnet) siempre visible.
- Centro (≈70 %): gráfico de velas en tiempo real (TradingView Lightweight Charts).
- Derecha: columna de agentes (tarjeta por agente: sesgo, confianza, estado, evidencia) y panel de síntesis.
- Abajo: panel con pestañas: Escenarios · Plan · Bitácora.
- T122 (2026-10-22), de arriba abajo: Río de decisión → **Mapa del sistema** (ya no es pantalla aparte) → **Operaciones sugeridas**: siempre tres posiciones #1–#3 para BTCUSDT; solo las ocupa una oportunidad validada (T49), las vacías dicen por qué y las ideas en observación van aparte como «pendientes de confirmación» → mesa. El **Historial de sugerencias** es la pestaña inferior inmediatamente después de «Bitácora». Solo BTCUSDT (sin selector de activo).
- Fila de capas activables: Canal, Niveles, Plan, Escenarios (activas por defecto); VWAP, Liquidaciones, Elliott, etc. (apagadas).

**El agente dibuja sobre el gráfico (en tiempo real, al cierre de cada vela; el precio actual se refresca por tick):**
- Soportes/resistencias como **zonas con grosor** (no líneas finas); canal o rango extendido hacia adelante.
- Plan: entrada, stop loss, take profit 1 y 2, relación riesgo/beneficio. Marcas de entradas/salidas pasadas. Al pasar el ratón sobre cualquier objeto: por qué existe (evidencia del agente).
- Deslizador de tiempo para reproducir decisiones pasadas.

**Escenarios (vista por defecto: trayectorias):** 3 (alcista/neutral/bajista) desde el precio actual, 20–30 velas, cada uno con trayectoria mediana + banda de incertidumbre + probabilidad (suman 100 %) + condición de invalidación. Colores: verde / azul / rojo con relleno suave. Interruptor opcional "Ver escenario como velas": muestra la secuencia OHLC simulada del escenario elegido (cuerpo lleno = sube, hueco = baja), etiquetada "simulada".

**Honestidad visible:** modo siempre rotulado; velas/trayectorias proyectadas rotuladas como simuladas; si el modelo no supera la línea base, la UI lo dice; cobertura y fuente de datos accesibles en cada panel.

**Técnico:** Vite + TypeScript, Lightweight Charts, WebSocket. Responsivo hasta tablet. Verificar con screenshot y leyendo los datos renderizados.
