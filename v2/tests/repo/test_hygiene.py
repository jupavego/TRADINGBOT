"""Nada sensible ni pesado en el árbol del repositorio (T121).

Mira lo que subiría un `git add -A` (versionado + sin seguir y no ignorado) y avisa si hay:
- una base DuckDB (`*.duckdb`, `*.duckdb.wal`…), o una suelta fuera de `v2/data/` aunque esté
  ignorada (una orden lanzada desde la carpeta equivocada crea un almacén nuevo donde no toca);
- un volcado de variables (`.env`, `*.env`, `env_EIM*`, o `"EIM_X": "…"` / `EIM_X=…` en un archivo
  de datos), como los paquetes de traslado y respaldo (`EIM_migracion/`, `env_EIM.json`);
- una clave en claro: `EIM_*KEY|SECRET|TOKEN|PASSWORD` asignada a un valor que parece real.

Las carpetas ignoradas enteras (`v2/data/`, `v2/backups/`, `EIM_migracion/`, `.venv/`) no se
abren: ahí los datos están donde deben. Si falla: muévelo fuera del repo o ignóralo en `.gitignore`.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # sin el repo de un hook
DUCKDB = re.compile(r"\.duckdb(\.wal|\.tmp)?$")
ENV_NAME = re.compile(r"(^|/)(\.env|[^/]*\.env|env_EIM[^/]*)$")
SECRET = re.compile(r"\bEIM_[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)\b[\"']?\s*[:=]\s*[\"']?"
                    r"[A-Za-z0-9+/_\-]{12,}")
DUMP = re.compile(r"\"EIM_[A-Z0-9_]+\"\s*:\s*\"|^\s*EIM_[A-Z0-9_]+=\S", re.M)
# El código y la documentación nombran variables (`EIM_COPY_SIM=off`), no las vuelcan
CODE = (".py", ".ps1", ".md", ".ts", ".js", ".html", ".css", ".vbs")
MAX_BYTES = 5_000_000


def _ls(root: Path, *args: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--exclude-standard", *args],
                         env=ENV, capture_output=True, check=True).stdout
    return [f for f in out.decode("utf-8").split("\0") if f]


def findings(root: Path) -> list[str]:
    """Problemas del árbol de `root`, uno por línea (vacío = limpio)."""
    found = []
    for f in _ls(root, "--others", "--ignored", "--directory"):  # ignorados sueltos
        if DUCKDB.search(f):
            found.append(f"{f}: base DuckDB fuera de v2/data/")
    for f in _ls(root, "--cached", "--others"):                  # lo que subiría `git add -A`
        p = root / f
        if DUCKDB.search(f):
            found.append(f"{f}: base DuckDB que git subiría")
        if ENV_NAME.search(f):
            found.append(f"{f}: archivo de variables que git subiría")
        if not p.is_file() or p.stat().st_size > MAX_BYTES:
            continue
        raw = p.read_bytes()
        if b"\0" in raw[:4096]:                                   # binario
            continue
        text = raw.decode("utf-8", errors="replace")
        if m := SECRET.search(text):
            found.append(f"{f}: clave en claro ({m.group(0)[:40]}…)")
        if not f.endswith(CODE) and (m := DUMP.search(text)):
            found.append(f"{f}: volcado de variables EIM_* ({m.group(0).strip()[:40]}…)")
    return found


def _git_ok(root: Path) -> bool:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                              env=ENV, capture_output=True).returncode == 0
    except OSError:
        return False


def test_the_tree_has_nothing_sensitive_or_heavy():
    if not _git_ok(REPO):
        pytest.skip("sin git o fuera de un checkout")
    problems = findings(REPO)
    assert not problems, ("en el árbol del repo hay datos o variables que no deben subir "
                          "(muévelos fuera del repo o ignóralos en .gitignore):\n"
                          + "\n".join(problems))


def test_planted_files_are_caught(tmp_path):
    if not _git_ok(REPO):
        pytest.skip("sin git")
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=ENV, check=True)
    (tmp_path / ".gitignore").write_text("*.duckdb\ndata/\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "reports.duckdb").write_bytes(b"ok: en su sitio")
    (tmp_path / "eim").mkdir()
    (tmp_path / "eim" / "reports.duckdb").write_bytes(b"\0suelta")
    (tmp_path / "reports.duckdb.wal").write_bytes(b"\0wal")
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    (tmp_path / "paquete.json").write_text('{"EIM_MACHINE": "equipo"}', encoding="utf-8")
    fake = "EIM_TESTNET_API_" + "SECRET=" + "Ab3dEf6hIj9kLm2nOp5q"     # partida: ni este archivo
    (tmp_path / "notas.txt").write_text(fake + "\n", encoding="utf-8")  # la lleva en claro
    (tmp_path / "doc.md").write_text("Define `EIM_TESTNET_API_KEY=…` y `EIM_COPY_SIM=off`.\n",
                                     encoding="utf-8")
    got = "\n".join(findings(tmp_path))
    assert "eim/reports.duckdb: base DuckDB fuera de v2/data/" in got
    assert "reports.duckdb.wal: base DuckDB que git subiría" in got
    assert ".env: archivo de variables" in got and "paquete.json: volcado" in got
    assert "notas.txt: clave en claro" in got
    assert "data/" not in got.replace("v2/data/", "") and "doc.md" not in got
