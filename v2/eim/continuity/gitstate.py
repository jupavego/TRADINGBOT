"""Estado del código frente al repositorio central (T125). Solo lectura: lo único que escribe
es `git fetch` (refs remotas). Nunca hace `pull`, `reset`, `checkout` ni `stash`: decide el
usuario, con lo que este módulo le enseña (trabajo sin confirmar, commits sin subir).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MAIN = "origin/main"


class GitFailed(RuntimeError):
    pass


def git(repo: Path, *args: str, timeout: float = 60.0, check: bool = True) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                             timeout=timeout, env=env, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        raise GitFailed(f"git {args[0]}: {e}") from e
    if check and out.returncode != 0:
        raise GitFailed(f"git {' '.join(args[:2])}: {(out.stderr or out.stdout).strip()[:300]}")
    return out.stdout


@dataclass
class Worktree:
    path: str
    branch: str
    dirty: list[str] = field(default_factory=list)
    local_only: int = 0               # commits que no están en ningún remoto


@dataclass
class CodeState:
    root: str
    branch: str
    head: str
    head_date: str
    remote_url: str
    fetched: bool
    fetch_error: str = ""
    ahead_main: int = 0               # commits de HEAD que no están en origin/main
    behind_main: int = 0              # commits de origin/main que no están en HEAD
    upstream: str = ""
    ahead_upstream: int = 0
    behind_upstream: int = 0
    worktrees: list[Worktree] = field(default_factory=list)
    local_only_branches: dict[str, int] = field(default_factory=dict)
    stashes: int = 0

    @property
    def unpublished(self) -> list[str]:
        """Trabajo que solo existe en este equipo (para el veredicto y el resumen)."""
        out = [f"{w.branch or w.path}: {len(w.dirty)} archivo(s) sin confirmar"
               for w in self.worktrees if w.dirty]
        out += [f"rama {b}: {n} commit(s) sin subir" for b, n in self.local_only_branches.items()]
        if self.stashes:
            out.append(f"{self.stashes} stash(es) locales")
        return out


def git_bytes(repo: Path, *args: str, timeout: float = 120.0) -> bytes:
    """Como `git`, pero sin decodificar (parches con contenido que no es UTF-8)."""
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                             timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise GitFailed(f"git {args[0]}: {e}") from e
    if out.returncode != 0:
        raise GitFailed(f"git {' '.join(args[:2])}: {out.stderr[:300]!r}")
    return out.stdout


def main_root(repo: Path) -> Path:
    """Carpeta del checkout principal aunque se llame desde un worktree."""
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    return Path(common).parent


def _count(repo: Path, *rng: str) -> int:
    try:
        return int(git(repo, "rev-list", "--count", *rng).strip() or 0)
    except (GitFailed, ValueError):
        return 0


def _dirty(path: Path) -> list[str]:
    try:
        return [ln[3:] for ln in git(path, "status", "--porcelain").splitlines() if ln.strip()]
    except GitFailed:
        return []


def worktrees(repo: Path) -> list[Worktree]:
    out, cur = [], {}
    for ln in git(repo, "worktree", "list", "--porcelain").splitlines() + [""]:
        if not ln.strip():
            if cur.get("worktree"):
                p = Path(cur["worktree"])
                br = cur.get("branch", "").removeprefix("refs/heads/")
                n = _count(p, "HEAD", "--not", "--remotes") if p.exists() else 0
                out.append(Worktree(str(p), br, _dirty(p) if p.exists() else [], n))
            cur = {}
            continue
        k, _, v = ln.partition(" ")
        cur[k] = v
    return out


def local_only_branches(repo: Path) -> dict[str, int]:
    heads = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    found = {}
    for b in heads:
        n = _count(repo, b, "--not", "--remotes")
        if n:
            found[b] = n
    return found


def state(repo: Path, *, fetch: bool = True, timeout: float = 90.0) -> CodeState:
    root = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    fetched, err = False, ""
    if fetch:
        try:
            git(root, "fetch", "--prune", "-q", "origin", timeout=timeout)
            fetched = True
        except GitFailed as e:
            err = str(e)
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = git(root, "rev-parse", "--short", "HEAD").strip()
    head_date = git(root, "log", "-1", "--format=%cI", "HEAD").strip()
    url = git(root, "remote", "get-url", "origin", check=False).strip()
    s = CodeState(str(root), branch, head, head_date, url, fetched, err)
    has_main = bool(git(root, "rev-parse", "--verify", "-q", MAIN, check=False).strip())
    if has_main:
        s.ahead_main = _count(root, f"{MAIN}..HEAD")
        s.behind_main = _count(root, f"HEAD..{MAIN}")
    up = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}",
             check=False).strip()
    if up and not up.startswith("@"):
        s.upstream = up
        s.ahead_upstream = _count(root, f"{up}..HEAD")
        s.behind_upstream = _count(root, f"HEAD..{up}")
    s.worktrees = worktrees(root)
    s.local_only_branches = local_only_branches(root)
    s.stashes = len(git(root, "stash", "list", check=False).splitlines())
    return s
