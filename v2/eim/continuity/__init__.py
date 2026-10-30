"""Continuidad entre equipos (T125): saber al arrancar si este equipo está al día y publicar
su estado al salir. No sustituye a nada: el código viaja por git, la experiencia por el repo
privado de T61/T117 (`eim.data.share`) y la copia completa es la de T115 (`eim.data.backup`);
aquí se añade la copia **fuera del disco** (`offsite`), la comprobación de arranque (`check`) y
el inventario de qué vive dónde (`inventory`). Procedimientos en `docs/CONTINUIDAD.md`.

CLI (desde `v2/`): `python -m eim.continuity check|publish|offsite …`.
"""
