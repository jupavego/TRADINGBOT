"""Opciones europeas: modelos mínimos y puros (T100). Sin red, sin disco, sin estado.

Por qué existe: el precio de una opción no se lee con indicadores técnicos. Lo que importa es su
**volatilidad implícita** (qué incertidumbre está pagando el mercado), sus **griegas** (de qué
depende su valor) y si la **cadena** de cotizaciones es coherente (sin arbitraje estático). Estos
módulos dan esas piezas con pruebas contra valores publicados; no son una clase de activo.

- `black_scholes`: Black–Scholes–Merton generalizado con costo de carry `b` (acciones,
  dividendos, divisas y futuros con Black-76) y sus griegas.
- `implied_vol`: volatilidad implícita con las cotas de no arbitraje comprobadas antes.
- `chain`: calidad de una cadena (diferenciales, cruces, monotonía, convexidad, paridad) y su
  resumen (volatilidad ATM y pendiente de la sonrisa): el agente de prueba de la familia.
"""
