"""T102 — la plataforma multiactivo en el catálogo del Observatorio, con textos llanos."""

from __future__ import annotations

from eim.observability import catalog as C

BUILT = ("instruments.registry", "data.class_sources", "scanner.service", "scanner.deep",
         "scanner.rank", "scanner.health", "scanner.rollout")
PLANNED = ("scanner.portfolio", "scanner.paper_adapter")


def test_multiasset_pieces_are_in_the_catalog():
    for cid in BUILT:
        assert C.get(cid) is not None and C.get(cid).built == "construido", cid
    for cid in PLANNED:
        assert C.get(cid) is not None and C.get(cid).built == "planeado", cid
    assert C.problems() == []


def test_the_chain_runs_from_the_registry_to_the_rollout():
    edges = {(s, d) for s, d, _ in C.edges()}
    for pair in (("scanner.service", "scanner.deep"), ("instruments.registry", "scanner.deep"),
                 ("scanner.deep", "scanner.rank"), ("scanner.rank", "scanner.health"),
                 ("data.class_sources", "scanner.health"), ("scanner.health", "scanner.rollout"),
                 ("scanner.rank", "scanner.portfolio"), ("scanner.portfolio",
                                                         "scanner.paper_adapter")):
        assert pair in edges, pair


def test_multiasset_components_run_on_demand_so_the_map_never_paints_them_without_data():
    for cid in BUILT[3:]:
        assert C.get(cid).cadence_s is None, cid
