"""Lo que la copia de T115 no lleva y solo existe en este equipo (T125): viaja como `extras/`
dentro de la copia externa.

- `git/`: estado del clon, un parche por worktree con cambios sin confirmar (+ sus archivos
  nuevos sin seguir, con tope) y un *bundle* de las ramas con commits que no están en ningún
  remoto. Se aplican con `git apply` / `git fetch <bundle>` (`docs/CONTINUIDAD.md` §6).
- `claude/<carpeta>/memory/`: la memoria de Claude de este clon y de sus worktrees.
- `data/`: estado pequeño fuera de las bases (identidad, configuración del transporte de
  experiencia, resumen de la copia simulada, escenarios de arbitraje, capturas de libros).

Nunca secretos: no se leen variables de entorno ni archivos de credenciales.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from eim.continuity.gitstate import (
    GitFailed,
    git,
    git_bytes,
    local_only_branches,
    main_root,
    worktrees,
)

MAX_FILE = 20 * 1024 * 1024
MAX_UNTRACKED = 100 * 1024 * 1024
DATA_FILES = ("machine_id", "share_config.json", "leaders/copy_sim.json", "leaders/hl_meta.json",
              "paper/arb_tests.json", "bots/quarantine.json")
DATA_DIRS = ("arb_history",)


def claude_slug(path: Path) -> str:
    """Nombre de la carpeta de proyecto de Claude Code para una ruta (todo lo que no es letra
    o dígito pasa a `-`)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _copy(src: Path, dst: Path) -> int:
    if not src.is_file() or src.stat().st_size > MAX_FILE:
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return src.stat().st_size


def _git_state(repo: Path, dest: Path) -> list[str]:
    notes, budget = [], MAX_UNTRACKED
    g = dest / "git"
    g.mkdir(parents=True, exist_ok=True)
    lines = [git(repo, "status", "-b", "--porcelain"), git(repo, "worktree", "list")]
    for w in worktrees(repo):
        if not w.dirty:
            continue
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(w.path).name)
        wt = Path(w.path)
        base = git(wt, "rev-parse", "HEAD").strip()
        (g / f"{name}.patch").write_bytes(git_bytes(wt, "diff", "--binary", "HEAD"))
        (g / f"{name}.base").write_text(f"{w.branch} {base}\n", encoding="utf-8")
        for rel in git(wt, "ls-files", "--others", "--exclude-standard").splitlines():
            src = wt / rel
            if src.is_file() and src.stat().st_size <= min(MAX_FILE, budget):
                budget -= _copy(src, g / "untracked" / name / rel)
        notes.append(f"{w.branch or name}: {len(w.dirty)} archivo(s) sin confirmar")
    only = local_only_branches(repo)
    if only:
        try:
            git(repo, "bundle", "create", str(g / "ramas_solo_locales.bundle"),
                *only, "--not", "--remotes", timeout=300)
            notes.append(f"bundle de {len(only)} rama(s) sin subir")
        except GitFailed as e:
            notes.append(f"bundle fallido: {e}")
    (g / "estado.txt").write_text("\n".join(lines + notes) + "\n", encoding="utf-8")
    return notes


def collect(dest: Path, repo: Path, data_dir: Path, home: Path | None = None) -> list[str]:
    """Llena `dest` y devuelve una línea por grupo copiado (para el registro)."""
    notes = []
    try:
        repo = main_root(repo)
        notes += _git_state(repo, dest)
    except GitFailed as e:
        notes.append(f"estado de git no disponible: {e}")
    projects = (home or Path.home()) / ".claude" / "projects"
    slug = claude_slug(repo)
    n_mem = 0
    for d in sorted(projects.glob(slug + "*")) if projects.exists() else []:
        for f in sorted((d / "memory").rglob("*")):
            if f.is_file():
                n_mem += bool(_copy(f, dest / "claude" / d.name / "memory" / f.relative_to(
                    d / "memory")))
    notes.append(f"memoria de Claude: {n_mem} archivo(s)")
    n_data = sum(bool(_copy(data_dir / rel, dest / "data" / rel)) for rel in DATA_FILES)
    for rel in DATA_DIRS:
        for f in sorted((data_dir / rel).rglob("*")) if (data_dir / rel).exists() else []:
            n_data += bool(_copy(f, dest / "data" / f.relative_to(data_dir)))
    notes.append(f"estado pequeño de data/: {n_data} archivo(s)")
    return notes
