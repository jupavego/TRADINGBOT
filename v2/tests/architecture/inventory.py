"""Inventario estático (AST) de los sitios que abren, modifican o cierran una posición (T114).

Una primitiva es una llamada que cambia una posición u orden real o simulada. Cada sitio se
identifica por (primitiva, archivo, función que la llama). El test compara el inventario con la
lista permitida: un sitio nuevo es un camino nuevo hacia una posición y debe pasar por la puerta
única (y registrarse aquí con su motivo).
"""

from __future__ import annotations

import ast
from pathlib import Path

EIM = Path(__file__).resolve().parents[2] / "eim"

# primitiva → (atributo o nombre llamado, receptores admitidos o None = cualquiera, carpeta o None)
PRIMITIVES: dict[str, tuple[str, tuple[str, ...] | None, str | None]] = {
    "orden al exchange": ("place", None, None),
    "arbitraje al exchange": ("place_arb", None, None),
    "orden firmada": ("post_order", None, None),
    "posición del bróker": ("Slot", None, None),
    "decisión del bróker": ("PaperDecision", None, None),
    "llenado del bróker": ("_fill", None, "paper/"),
    "cancelación del bróker": ("_cancel", None, "paper/"),
    "cierre del bróker": ("_close", None, "paper/"),
    "cierre rechazado del bróker": ("_reject", None, "paper/"),
    "relleno de la copia": ("fill", ("acc", "self.account", "account"), "copytrading/"),
    "orden de la copia": ("_execute", ("self",), "copytrading/"),
    "cierre testnet": ("flatten", ("svc", "self", "rt.svc"), None),
    "cierre de todo el arbitraje": ("flatten_all", None, None),
    "cierre de un arbitraje": ("close", ("ex", "self.ex", "r.ex", "self"), None),
    "rebalanceo de arbitraje": ("rebalance", ("ex", "self.ex", "r.ex"), None),
}
SCOPE = ("execution", "paper", "copytrading", "api", "operation", "risk", "leaders", "bots",
         "arbitrage", "data")


def _sources() -> list[Path]:
    return sorted(p for p in EIM.rglob("*.py") if p.relative_to(EIM).parts[0] in SCOPE)


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel, self.stack, self.sites = rel, [], set()

    def _fn(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _fn

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        name, recv = (f.attr, ast.unparse(f.value)) if isinstance(f, ast.Attribute) else (
            (f.id, None) if isinstance(f, ast.Name) else (None, None))
        for prim, (target, recvs, folder) in PRIMITIVES.items():
            if name == target and (recvs is None or recv in recvs) and (
                    folder is None or self.rel.startswith(folder)):
                self.sites.add((prim, self.rel, ".".join(self.stack) or "<módulo>"))
        self.generic_visit(node)


def inventory() -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for p in _sources():
        v = _Visitor(p.relative_to(EIM).as_posix())
        v.visit(ast.parse(p.read_text(encoding="utf-8")))
        out |= v.sites
    return out


if __name__ == "__main__":   # para revisar a mano: python -m tests.architecture.inventory
    for s in sorted(inventory()):
        print(s)
