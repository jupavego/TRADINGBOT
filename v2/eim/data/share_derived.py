"""Derivados que se recalculan tras importar (T61): los veredictos de la puerta de validación
(Holm sobre la UNIÓN de intentos). Pronósticos, tablero de líderes e informes se regeneran solos
con la operación normal. Nunca se importan ya calculados."""

from __future__ import annotations

from pathlib import Path


def recompute(data_dir: Path) -> list[str]:
    """Recalcula `val_verdicts` con el código y los datos locales. Devuelve mensajes; si faltan
    velas locales (equipo nuevo) lo dice y deja el comando para hacerlo después."""
    if not (data_dir / "paper.duckdb").exists():
        return ["sin paper.duckdb: nada que recalcular"]
    from eim.data.paper_store import PaperStore
    from eim.data.store import Store
    from eim.data.validation_store import ValidationStore
    from eim.paper.desk import PaperDesk
    from eim.validation.service import Validator

    ps = PaperStore(data_dir / "paper.duckdb")
    msgs = []
    try:
        desk = PaperDesk(Store(data_dir), ps)
        validator = Validator(desk, ValidationStore(ps))
        for sym in desk.symbols:
            out = validator.compute(sym)
            msgs.append(f"veredictos recalculados {sym}: {out['attempts']} intentos registrados")
    except Exception as exc:  # sin velas locales, etc.: no invalida la importación ya hecha
        msgs.append(f"no se pudieron recalcular los veredictos ({type(exc).__name__}: {exc}); "
                    "cuando haya velas locales: python -m eim.validation")
    finally:
        ps.close()
    return msgs
