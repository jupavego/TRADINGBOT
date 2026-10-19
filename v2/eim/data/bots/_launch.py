"""Lanzador del ejecutor aislado (POSIX): fija límites de recursos y hace `exec` del bot.

Uso: `python -I _launch.py <memoria_mb> <cpu_s> <bytes_salida> <comando…>`. Corre antes del bot,
con su mismo entorno limpio. No importa nada de EIM.
"""

import os
import resource
import sys


def main() -> None:
    mem_mb, cpu_s, max_out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    for res, value in ((resource.RLIMIT_AS, mem_mb * 1024 * 1024), (resource.RLIMIT_CPU, cpu_s),
                       (resource.RLIMIT_FSIZE, max_out), (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(res, (value, value))
        except (ValueError, OSError):
            pass  # el sistema no deja bajarlo: el timeout sigue siendo la red de seguridad
    cmd = sys.argv[4:]
    os.execv(cmd[0], cmd)


if __name__ == "__main__":
    main()
