"""Rutas de solo lectura del escuadrón de bots (T57): señales guardadas y catálogo utilizable."""

from __future__ import annotations

from statistics import pstdev

from fastapi import APIRouter, HTTPException, Query

from eim.bots.card import default_cards
from eim.bots.scorer import BotScorer
from eim.bots.service import BotService
from eim.core import BotSignal
from eim.data.bots.store import BotSignalStore
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.synthesis.squad import SquadPolicy, current_policy, key_of, support

MODE_NOTE = "ANALISIS: los bots solo opinan; no tienen voto en la síntesis ni envían órdenes"


LABEL = "Señal de un bot externo · no es una operación"


def squad_view(rows: list[BotSignal], cards: dict, sc: dict | None, policy: SquadPolicy | None,
               quarantined: dict[str, dict]) -> dict:
    """Fila por bot (postura vigente + concepto de T59), discrepancia y apoyo por dirección."""
    concept = {key_of(c["bot"], c["strategy"]): c for c in (sc or {}).get("bots", [])}
    latest: dict[str, BotSignal] = {}
    for s in rows:      # ascendentes por asof: la última de cada bot-estrategia gana
        latest[key_of(s.bot_id, s.strategy)] = s
    out = []
    for key, s in sorted(latest.items()):
        c, b = concept.get(key), (policy.get(key) if policy else None)
        card = cards.get(s.bot_id)
        q = quarantined.get(key)
        state = "cuarentena" if q else (c["state"] if c else "sin_puntuar")
        out.append({
            "key": key, "bot_id": s.bot_id, "name": card.name if card else s.bot_id,
            "strategy": s.strategy, "class": card.bot_class if card else None,
            "lane": bool(card and card.bot_class == "L"), "stance": s.stance,
            "confidence": s.confidence, "signal_status": s.status, "asof": s.asof,
            "evidence": s.evidence, "state": state, "votes": bool(b and b.votes),
            "weight": b.weight if b else 0.0, "publicable": bool(c and c["publicable"]),
            "modulates": bool(c and c["modulates_confidence"]),
            "version": s.version, "dimensions": c["dimensions"] if c else None,
            "reasons": ([f"cuarentena: {q['reason']}"] if q else []) + (
                c["reasons"] if c else ["sin puntuar (T59): el bot se ve pero no vota"]),
            "coverage": s.data_quality.coverage, "label": LABEL})
    ok = [r for r in out if r["signal_status"] == "ok" and not r["lane"]]
    stances = [r["stance"] for r in ok]
    return {
        "mode": MODE_NOTE, "label": LABEL, "bots": out,
        "disagreement": float(pstdev(stances)) if len(stances) >= 2 else None,
        "support": support([{"stance": r["stance"], "status": "ok"} for r in ok]),
        "scored_symbol": (sc or {}).get("symbol"), "scored_asof": (sc or {}).get("asof"),
        "channels": {"vote": bool(policy and policy.voters),
                     "confidence": bool(policy and policy.modulating),
                     "second_opinion": True},
        "quarantine": quarantined}


BOT_STORE_TFS = ("5m",)   # marcos con posturas guardadas que no son de la UI


def build_bots_router(store: BotSignalStore, service: BotService,
                      scorer: BotScorer | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/v2/bots")
    def squad(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        """El escuadrón hoy: postura vigente de cada bot, estado/dimensiones de T59, discrepancia y
        apoyo por dirección. Solo lectura: ningún bot pide tamaño, apalancamiento ni órdenes."""
        if symbol not in SYMBOLS or tf not in TF_MS:
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")
        rows = store.query(symbol, tf, limit=40)
        sc = scorer.scores.latest(scorer.symbols[0], scorer.crit.version) if scorer else None
        q = service.quarantine.entries() if service.quarantine is not None else {}
        return {"symbol": symbol, "timeframe": tf,
                **squad_view(rows, default_cards(), sc, current_policy(), q)}

    @router.get("/v2/bots/signals")
    def signals(symbol: str = "ETHUSDT", tf: str = "1h", bot: str | None = None,
                start: int | None = None, end: int | None = None,
                limit: int = Query(200, ge=1, le=2000)) -> dict:
        """Posturas guardadas. Admite también `5m` (marco de NFI, solo de almacén): se sirven
        las filas de `bot_signals`, no se calcula nada."""
        if symbol not in SYMBOLS or (tf not in TF_MS and tf not in BOT_STORE_TFS):
            raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")
        rows = store.query(symbol, tf, start, end, bot, limit)
        return {"mode": MODE_NOTE, "signals": [s.model_dump() for s in rows]}

    @router.get("/v2/bots/catalog")
    def catalog() -> dict:
        active = {a.bot_id for a in service.adapters}
        cards = [{"id": c.id, "name": c.name, "repo": c.repo, "commit_sha": c.commit_sha,
                  "license": c.license.spdx, "mode": c.integration_mode, "class": c.bot_class,
                  "verdict": c.verdict, "approval": c.approval.state,
                  "security_enabled": c.security.enabled, "usable": c.usable,
                  "adapter_active": c.id in active}
                 for c in default_cards().values() if c.usable]
        return {"mode": MODE_NOTE, "bots": cards}

    @router.get("/v2/bots/scorecard")
    def scorecard(symbol: str = "BTCUSDT") -> dict:
        """Tabla de puntuación vigente (T59), solo lectura: estado y cuatro dimensiones por bot,
        intentos de la puerta y condiciones por régimen. Siempre SIMULADO."""
        if symbol not in SYMBOLS:
            raise HTTPException(400, f"símbolo no soportado: {symbol}")
        if scorer is None:
            raise HTTPException(503, "puntuación de bots no disponible")
        return {"mode": "SIMULADO", **scorer.latest(symbol), "error": scorer.error}

    return router
