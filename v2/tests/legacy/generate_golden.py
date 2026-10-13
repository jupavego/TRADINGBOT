"""Regenera los golden outputs: `python -m tests.legacy.generate_golden` (desde v2/).

Solo regenerar al cambiar el comportamiento del legado A PROPÓSITO.
"""
from tests.legacy._runner import generate

if __name__ == "__main__":
    generate()
