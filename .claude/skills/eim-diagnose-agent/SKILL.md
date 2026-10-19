---
name: eim-diagnose-agent
description: Diagnostica por qué un agente EIM sale «sin datos»/degradado y lo pone operativo. Úsalo cuando una esfera de la interfaz diga «sin datos» o un agente devuelva no_data.
---

# Diagnosticar un agente EIM sin datos (desde `v2/`)

Cadena fija; no saltes eslabones, cada causa con evidencia (archivo:línea o salida real):
1. **Qué pide el agente:** `eim/agents/<id>/agent.py` → campos del snapshot que lo llevan a `no_data_report` (y `requires`).
2. **Quién llena ese campo:** `eim/data/snapshot.py::build_snapshot`. Campo que no aparece ahí = nunca llega en vivo (hubo casos: liquidaciones, titulares).
3. **Quién escribe el dato:** proveedor/colector/sync. ¿Lo llama el ciclo (`operation/cycle.py::_sync*`) o un servicio de `scripts/servicio_continuo.ps1`? ¿Tiene latido (`hooks_service.beat`) y catálogo (`observability/catalog`)?
4. **Fuente viva:** comprobar que la fuente sigue existiendo (p. ej. Binance retiró `liquidationSnapshot` en oct-2024). Fuentes de referencia en `repos/repo_profiles_master.md` (grep por nombre).
5. **Umbral de acumulación:** `min_*` de `params.py` (velas con datos) → cuánto tarda en salir de «sin datos».
6. **Registro:** que el agente esté en `agents/registry.py` con dependencias inyectadas (p. ej. `ContextAgent()` sin analizador = siempre `no_data`).
7. **En el equipo del usuario:** proceso corriendo, carpeta `data/…` con Parquet, latido reciente.

Arreglo: el agente sigue puro (sin red/disco). Lectura en `eim/data/<x>.py` sin red; red solo en `sync_*`/colector; campo aditivo en `MarketSnapshot`; `sources`/`coverage` reales; «0» solo si hay prueba de vida del colector, si no, sin dato. Cierra con tests sin red, catálogo (`eim-new-agent` paso 7) y el gate: `python -m ruff check eim tests && python -m pytest -q`.
