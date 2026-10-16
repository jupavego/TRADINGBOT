"""Parámetros de la captura de líderes (T40). Límites oficiales de Hyperliquid en T33 §1."""

from __future__ import annotations

SOURCE = "hyperliquid"
HLP_VAULT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"  # creador de mercado del exchange

# --- Límites del exchange -------------------------------------------------------------------
WS_MAX_USERS = 10  # usuarios únicos por IP en suscripciones de usuario; el resto, por REST
REST_WEIGHT_PER_MIN = 600  # la mitad del límite por IP (1200) para convivir con otros procesos
FILLS_PAGE = 2000  # máximo por respuesta de userFills/userFillsByTime
FUNDING_PAGE = 500  # máximo por respuesta de userFunding

# --- Ritmos del servicio (segundos) ---------------------------------------------------------
RECON_EVERY_S = 30.0  # reconciliación de posiciones (esperado vs exchange)
POLL_EVERY_S = 60.0  # ejecuciones por REST de los líderes sin WS
FUNDING_EVERY_S = 600.0  # pagos de funding (se liquidan cada hora)
PING_EVERY_S = 30.0  # el servidor cierra conexiones sin tráfico en 60 s
BACKOFF_MAX_S = 60.0

# --- Historial ------------------------------------------------------------------------------
BOOT_LOOKBACK_MS = 86_400_000  # al empezar a seguir un líder: último día de historial
MAX_PAGES = 5  # por consulta paginada (≤ 10 000 ejecuciones; el resto lo cubre T41)
BACKFILL_MARGIN_MS = 5_000  # se pide desde un poco antes del corte (dedupe absorbe repetidos)
SNAPSHOT_KEEP_MS = 5 * 60_000  # foto de posiciones aunque no cambie (< POSITIONS_MAX_AGE)
POSITIONS_MAX_AGE_MS = 10 * 60_000  # una foto más vieja no se usa como estado vigente
SEEN_KEEP = 5_000  # claves (tid, oid) recordadas por líder para descartar repetidos

# --- Reconciliación -------------------------------------------------------------------------
ENTRY_REL_TOL = 1e-3  # el precio medio del exchange viene redondeado
RECON_RETRY_S = 5.0  # `userFillsByTime` llegó a ir >3 s por detrás del estado (2026-10-15)
RECON_RETRIES = 3  # re-comprobaciones del mismo estado antes de resincronizar

# --- Descubrimiento (no es evaluación: T41 puntúa) ------------------------------------------
DISCOVERY_COINS = ("BTC", "ETH")
DISCOVERY_MIN_TRADES = 3
DISCOVERY_MIN_NOTIONAL = 50_000.0  # USD vistos en la muestra
DISCOVERY_MIN_TAKER_SHARE = 0.10  # descarta creadores de mercado puros (no se copian)
DISCOVERY_TOP = 20
EXCLUDED = frozenset({"0x" + "0" * 40, HLP_VAULT})
