"""T123: ninguna cola sin tope en la tubería, y el inventario coincide con el código.

Recorre el código de la tubería viva (recolectores → instantánea → agentes → síntesis → plan,
más el observatorio que la mide) y falla si aparece una cola sin tamaño máximo, un ejecutor con
cola interna sin tope o una conexión WebSocket sin `max_queue` declarado. Lo que se acota por
otro medio va en `ALLOWED` con su motivo escrito.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eim.observability import queues

V2 = Path(__file__).resolve().parents[2]
PIPELINE = ("eim/data/collectors", "eim/data/snapshot.py", "eim/api/live.py",
            "eim/api/sources.py", "eim/api/main.py", "eim/agents", "eim/synthesis",
            "eim/operation/cycle.py", "eim/operation/supervisor.py", "eim/observability")
QUEUES = {"Queue", "LifoQueue", "PriorityQueue", "JoinableQueue"}
UNBOUNDED = {"SimpleQueue"}                          # no admiten tope: prohibidas
EXECUTORS = {"ThreadPoolExecutor", "ProcessPoolExecutor"}   # su cola interna no tiene tope
# (archivo, constructor) → por qué está acotado aunque el constructor no lo diga
ALLOWED = {
    ("eim/data/collectors/hft_writer.py", "ThreadPoolExecutor"):
        "un hilo; los volcados pendientes los acota `hft.escritor` (el consumidor frena)",
    ("eim/data/collectors/hft_writer.py", "deque"):
        "seguimiento de los volcados del ejecutor; acotado por `hft.escritor`",
}


def _name(fn: ast.expr) -> str:
    return fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _zero(node: ast.expr | None) -> bool:
    return node is None or (isinstance(node, ast.Constant) and node.value in (0, None))


def violations(source: str, rel: str) -> list[str]:
    """Colas sin tope en `source` (texto de un módulo), como «archivo:línea qué»."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name, where = _name(node.func), f"{rel}:{node.lineno}"
        if (rel, name) in ALLOWED:
            continue
        if name in UNBOUNDED:
            out.append(f"{where} {name}: no admite tope")
        elif name in QUEUES and _zero(node.args[0] if node.args else _kw(node, "maxsize")):
            out.append(f"{where} {name} sin maxsize")
        elif name == "deque" and _zero(node.args[1] if len(node.args) > 1
                                       else _kw(node, "maxlen")):
            out.append(f"{where} deque sin maxlen")
        elif name in EXECUTORS:
            out.append(f"{where} {name}: cola interna sin tope")
        elif name.endswith("connect") and _kw(node, "ping_interval") is not None \
                and _kw(node, "max_queue") is None:
            out.append(f"{where} WebSocket sin max_queue declarado")
    return out


def _files() -> list[Path]:
    out = []
    for p in PIPELINE:
        path = V2 / p
        out += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    return out


def test_no_unbounded_queue_in_the_pipeline():
    files = _files()
    assert len(files) > 40, "la lista de la tubería no encuentra sus módulos"
    found = [v for f in files
             for v in violations(f.read_text(encoding="utf-8"), f.relative_to(V2).as_posix())]
    assert not found, "colas sin tope en la tubería (T123):\n" + "\n".join(found)


@pytest.mark.parametrize("src, bad", [
    ("import asyncio\nq = asyncio.Queue()", True),
    ("import asyncio\nq = asyncio.Queue(maxsize=0)", True),
    ("import queue\nq = queue.SimpleQueue()", True),
    ("from collections import deque\nd = deque()", True),
    ("from collections import deque\nd = deque([1, 2])", True),
    ("from concurrent.futures import ThreadPoolExecutor\np = ThreadPoolExecutor(2)", True),
    ("import websockets\nw = websockets.connect(u, ping_interval=20)", True),
    ("import asyncio\nq = asyncio.Queue(256)", False),
    ("import asyncio\nq = asyncio.Queue(maxsize=n)", False),
    ("from collections import deque\nd = deque(maxlen=5)", False),
    ("from collections import deque\nd = deque([1], 5)", False),
    ("import websockets\nw = websockets.connect(u, ping_interval=20, max_queue=16)", False),
])
def test_the_scanner_catches_what_it_should(src, bad):
    assert bool(violations(src, "x.py")) is bad


def test_every_frontier_declares_size_policy_and_reason():
    from eim.observability.catalog import COMPONENTS
    ids = {c.id for c in COMPONENTS}
    assert len(queues.BY_ID) == len(queues.FRONTIERS)
    for f in queues.FRONTIERS:
        assert f.capacity > 0 and f.policy in queues.POLICY_ES, f.id
        assert len(f.why_es) >= 40 and f.title_es and f.unit, f.id
        assert f.component_id in ids, f"{f.id}: {f.component_id} no está en el catálogo"


def test_code_constants_match_the_inventory():
    from eim.data.collectors import hft_ws
    from eim.data.collectors.writer import HourlyWriter
    from eim.observability import thresholds
    assert hft_ws.QUEUE_MAX == queues.capacity("hft.recepcion") == hft_ws.Inbox().q.maxsize
    assert hft_ws.WRITE_BACKLOG_MAX == queues.capacity("hft.escritor")
    assert thresholds.QUEUE_MAX == queues.capacity("obs.emisor")
    assert HourlyWriter.__init__.__defaults__[0] == queues.capacity("micro.escritor")


def test_the_written_inventory_names_every_frontier():
    note = V2.parent / "PLAN" / "notas" / "T123_colas.md"
    text = note.read_text(encoding="utf-8")
    missing = [f.id for f in queues.FRONTIERS if f"`{f.id}`" not in text]
    assert not missing, f"fronteras sin fila en {note.name}: {missing}"
