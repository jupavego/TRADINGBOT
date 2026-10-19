"""Informe de importación (T61): por tabla y por máquina de origen, qué es nuevo, qué ya estaba,
qué choca y qué no es compatible. Es el mismo en simulacro y con `--apply`."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from eim.data.share_merge import Result


@dataclass
class Report:
    import_id: str
    apply: bool
    machine: str
    exports: list[dict] = field(default_factory=list)      # {machine, created_at, path}
    results: list[Result] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)     # {machine, path, problems}
    backup: str | None = None
    notes: list[str] = field(default_factory=list)

    def totals(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for r in self.results:
            t = out.setdefault(r.tbl, {"new": 0, "dup": 0, "conflict": 0, "incompatible": 0})
            for k in t:
                t[k] += getattr(r, k)
        return out

    def to_json(self) -> dict:
        return {"import_id": self.import_id, "applied": self.apply, "machine": self.machine,
                "exports": self.exports, "results": [r.to_json() for r in self.results],
                "totals": self.totals(), "rejected": self.rejected, "backup": self.backup,
                "notes": self.notes}

    def write(self, data_dir: Path) -> Path:
        p = data_dir / "share" / f"import_{self.import_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")
        return p

    def render(self) -> str:
        head = ("IMPORTACIÓN APLICADA" if self.apply
                else "SIMULACRO (no se escribió nada; usa --apply para aplicar)")
        lines = [f"{head} · {self.import_id} · destino: {self.machine} · modo SIMULADO", ""]
        if not self.exports:
            lines.append("No hay exportaciones de otras máquinas para importar.")
        for e in self.exports:
            lines.append(f"origen {e['machine']}  {e['created_at']}  {e['path']}")
        for r in self.rejected:
            lines.append(f"RECHAZADA {r['machine']} {r['path']}: " + "; ".join(r["problems"]))
        shown = [r for r in self.results if r.new or r.dup or r.conflict or r.incompatible]
        if self.results and not shown:
            lines.append("\nLas exportaciones no traen filas en ninguna tabla compartida.")
        if shown:
            lines += ["", f"{'tabla':<18}{'origen':<20}{'nuevas':>10}{'ya estaban':>12}"
                          f"{'conflicto':>11}{'incompat.':>11}"]
            for r in shown:
                lines.append(f"{r.tbl:<18}{r.src:<20}{r.new:>10}{r.dup:>12}{r.conflict:>11}"
                             f"{r.incompatible:>11}" + (f"  ({r.note})" if r.note else ""))
            lines += ["", "Total por tabla (nuevas / ya estaban / conflicto / incompatibles):"]
            for t, v in self.totals().items():
                if not any(v.values()):
                    continue
                lines.append(f"  {t:<18}{v['new']:>8}{v['dup']:>8}{v['conflict']:>8}"
                             f"{v['incompatible']:>8}")
        if any(r.conflict for r in self.results):
            lines.append("\nConflicto = misma clave y contenido distinto: se conservó lo local; el "
                         "detalle está en la tabla share_conflicts.")
        lines += [f"\ncopia previa: {self.backup}" if self.backup else "", *self.notes]
        return "\n".join(x for x in lines if x is not None)
