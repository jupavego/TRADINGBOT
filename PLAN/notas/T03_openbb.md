# T03 — ¿OpenBB como fuente secundaria?

**Conclusión: no integrarlo ahora.** Evaluación basada en conocimiento general de la plataforma (no se instaló ni se probó en esta tarea).

## Qué es
OpenBB Platform es una capa Python que unifica decenas de proveedores (FMP, Polygon, FRED, yfinance, etc.) bajo una API común.

## Utilidad para EIM
- **Macro / acciones / FX / commodities** (DXY, SPX, oro, tasas, FRED): útil como contexto para `agents/context` o correlaciones. Ninguno es necesario para el MVP (BTC/ETH perpetuos).
- **Cripto de derivados** (funding, OI, liquidaciones, order book): cobertura débil o dependiente de proveedores de pago; Binance directo ya da datos primarios con mejor frescura y control.
- **Costo**: dependencia pesada (muchas extensiones), claves de API de terceros y licencias por proveedor; choca con la regla de "toda cifra expone su `source` y cobertura real" porque abstrae el origen.

## Riesgos
Cambios de API entre versiones, límites de cuota de los proveedores gratuitos, latencia y datos retrasados presentados como actuales.

## Recomendación
Mantener la interfaz `Provider` (T03) como punto de extensión. Si se necesita macro (T24 contexto), añadir un proveedor mínimo directo (FRED o yfinance) detrás de `Provider`, no OpenBB completo. Revisar licencia/seguridad según T04 antes de cualquier adopción.
