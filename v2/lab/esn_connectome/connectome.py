"""Extracción de un subgrafo del conectoma FlyWire (v783) para usarlo como reservorio.

Fuente: FlyWire Consortium, `proofread_connections_783.feather`, Zenodo 10.5281/zenodo.10676866,
licencia CC BY 4.0 (Dorkenwald et al. 2024, Schlegel et al. 2024, Nature). El archivo completo
(852 MB) NO se versiona; solo el subgrafo resultante (`data/subgraph_1000.npz`).

Selección: se suman las sinapsis por par (pre→post) sobre todos los neuropilos; se parte de la
neurona con más sinapsis totales y se añade de forma voraz la neurona con más sinapsis hacia/desde
el conjunto actual. El orden de inclusión se guarda, de modo que los prefijos de 100/300/500
neuronas también son subgrafos conexos.

Signo por neurona presináptica (neurotransmisor predicho dominante, ponderado por sinapsis):
ACh → excitadora (+); GABA y glutamato → inhibidoras (−) (convención habitual en modelos de
Drosophila); DA/SER/OCT (moduladoras) → + por simplicidad.

Uso: `python -m lab.esn_connectome.connectome --src C:/t28data/proofread_connections_783.feather`
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
SUBGRAPH = HERE / "data" / "subgraph_1000.npz"
NT_COLS = ("ach_avg", "gaba_avg", "glut_avg", "oct_avg", "ser_avg", "da_avg")
INHIBITORY = {"gaba_avg", "glut_avg"}


def extract(src: Path, n_max: int = 1000) -> dict[str, np.ndarray]:
    import pandas as pd
    from scipy import sparse

    df = pd.read_feather(src)
    cols = ["pre_pt_root_id", "post_pt_root_id", "syn_count"]
    nts = [c for c in NT_COLS if c in df.columns]
    df = df[cols + nts]
    for c in nts:
        df[c] = df[c] * df["syn_count"]
    pair = df.groupby(["pre_pt_root_id", "post_pt_root_id"], sort=False).sum().reset_index()
    pre_nt = pair.groupby("pre_pt_root_id")[nts].sum()
    dominant = pre_nt.idxmax(axis=1)
    sign_of = dominant.map(lambda c: -1 if c in INHIBITORY else 1)

    ids = np.unique(np.concatenate([pair["pre_pt_root_id"], pair["post_pt_root_id"]]))
    pos = {v: i for i, v in enumerate(ids)}
    r = pair["pre_pt_root_id"].map(pos).to_numpy()
    c = pair["post_pt_root_id"].map(pos).to_numpy()
    w = pair["syn_count"].to_numpy(dtype=float)
    a = sparse.csr_matrix((w, (r, c)), shape=(len(ids), len(ids)))
    s = (a + a.T).tocsc()

    seed = int(np.asarray(s.sum(axis=0)).ravel().argmax())
    order = [seed]
    taken = np.zeros(len(ids), dtype=bool)
    taken[seed] = True
    score = s[:, seed].toarray().ravel()
    while len(order) < n_max:
        score[taken] = -1
        nxt = int(score.argmax())
        order.append(nxt)
        taken[nxt] = True
        score += s[:, nxt].toarray().ravel()

    idx = np.array(order)
    sub = a[idx][:, idx].toarray()  # sub[pre, post]
    signs = np.array([sign_of.get(ids[i], 1) for i in idx], dtype=float)
    signed = (sub * signs[:, None]).T  # W[post, pre]
    return {
        "root_ids": ids[idx].astype(np.int64),
        "signed_syn": signed.astype(np.float32),
        "signs": signs.astype(np.int8),
    }


def load(n: int) -> np.ndarray:
    """Matriz `W[post, pre]` con sinapsis con signo para las primeras `n` neuronas."""
    d = np.load(SUBGRAPH)
    m = d["signed_syn"]
    if n > m.shape[0]:
        raise ValueError(f"el subgrafo guardado tiene {m.shape[0]} neuronas, se pidieron {n}")
    return m[:n, :n].astype(float)


def describe(m: np.ndarray) -> dict[str, float]:
    mask = m != 0
    n = m.shape[0]
    pres = np.abs(m).sum(axis=0) > 0
    inhib = (m < 0).any(axis=0)
    return {
        "n": n,
        "edges": int(mask.sum()),
        "density": float(mask.mean()),
        "synapses": float(np.abs(m).sum()),
        "inhibitory_pre_frac": float(inhib[pres].mean()) if pres.any() else 0.0,
        "reciprocal_frac": float((mask & mask.T).sum() / max(mask.sum(), 1)),
    }


def main() -> None:  # pragma: no cover - uso manual con el archivo descargado
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--n", type=int, default=1000)
    args = ap.parse_args()
    out = extract(args.src, args.n)
    SUBGRAPH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(SUBGRAPH, **out)
    for k in (100, 300, 500, args.n):
        print(k, describe(out["signed_syn"][:k, :k].astype(float)))


if __name__ == "__main__":  # pragma: no cover
    main()
