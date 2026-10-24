# EIM — Agente de trading de futuros (BTC/ETH)

> Colaboradores nuevos: ver `ONBOARDING.md` (instalación, flujo con ramas/PR, config de Claude).

Sistema de inteligencia estructural de mercado → agente multiagente de trading. Documentos F0–F6 = especificación vinculante (F0 `MSI-META-001.md` es la constitución; el código no puede contradecirla). **`v2/` = código NUEVO (aquí vive todo: `v2/eim/`, `v2/tests/`, `v2/pyproject.toml`); toda ruta `eim/`, `tests/`, `pyproject.toml` de `PLAN/` es relativa a `v2/`.** Lo previo (`F0`–`F7`, `repos/`) NO se mezcla con v2. `legacy/F7/` = código legado archivado en T32 (solo oráculo de regresión; no se edita; ver `legacy/README.md`). `repos/` = referencias; perfiles en `repos/repo_profiles_master.md` (grep por nombre, no leer entero).

## Protocolo de sesión (ahorra tokens)
1. Tu tarea está en `PLAN/Txx.md`. Lee SOLO ese archivo y los archivos que él lista. No explores el repo en general.
2. Verifica prerrequisitos en `PLAN/STATUS.md`; si faltan, detente y avisa.
3. No amplíes el alcance. Lo que quede fuera → una línea en `PLAN/BACKLOG.md`.
4. Antes de terminar: corre el gate (desde `v2/`: `python -m ruff check eim tests && python -m pytest -q`), cumple los criterios de aceptación y marca la tarea en `PLAN/STATUS.md` con 2–3 líneas (qué quedó y dónde). Al marcar el estado, cambia ☐→◐ al empezar y ◐→☑ al terminar, y luego corre `python PLAN/build_roadmap.py` para refrescar `PLAN/roadmap.html`. Ese comando también publica la hoja de ruta en la carpeta viva `v2/data/roadmap_live/` del checkout principal, que es la que sirve el icono del escritorio (`http://127.0.0.1:8765/roadmap.html`): se actualiza en vivo desde cualquier worktree, sin servidores nuevos ni esperar a fusionar, siempre que la rama contenga `origin/main` (si está atrasada no publica: trae `main` y repítelo).
5. Archivos legados grandes (`legacy/F7/eim_engine.py`, `legacy/F7/web/index.html`): Grep/offset, nunca lectura completa.
6. Contratos de datos: `PLAN/CONTRATOS.md`. Especificación de interfaz: `PLAN/UI_SPEC.md` (solo tareas de UI).

## Arquitectura (resumen)
Detalle y operación en `v2/docs/`: `ARQUITECTURA.md`, `OPERACION.md` (arranque, copias, versionado, dependencias), `RUNBOOK.md` (incidentes), `NUEVO_AGENTE.md`, `SEGURIDAD.md`.
`eim/core` contratos (pydantic) · `data` proveedores+almacén DuckDB · `agents/<nombre>` analizadores puros · `forecast` · `synthesis` · `risk` · `execution` · `backtest` · `api` FastAPI+WS · `web` Vite+TS+Lightweight Charts.
Contrato central: `Agent.run(MarketSnapshot) -> AgentReport` (sesgo −1..+1, confianza 0..1, horizonte, evidencia, métricas, advertencias, overlays).

## Reglas de código
- Identificadores en inglés; docstrings, UI y documentos en español.
- Los agentes son funciones puras sobre el snapshot: sin red, sin disco, sin estado global. Todo I/O vive en `data/`.
- Archivos ≤ 300 líneas; un agente = un paquete con `agent.py`, `params.py`, tests.
- Tests sin red (fixtures en `tests/fixtures/`). Tests de regresión contra el legado al migrar.
- Nunca presentar datos asumidos como reales: toda cifra expone su `source` y su cobertura real.
- La proyección de precio es SIEMPRE probabilística (3 escenarios con probabilidad + bandas); jamás una línea única sin incertidumbre. Las velas proyectadas se etiquetan "simuladas".
- Los LLM solo informan (`agents/context`). Riesgo y ejecución son código determinista con poder de veto.
- Toda vista de plan/operación muestra el modo: Análisis, Simulado o Testnet. Sin dinero real hasta superar la puerta de edge (T27) y semanas de paper trading (T31).
- Verificar gráficos inspeccionando datos renderizados o con screenshot, no solo "sin errores en consola".
- Código de terceros: revisar licencia y seguridad antes de copiar (ver T04). Solo claves de testnet sin permiso de retiro.

## Comandos
- Gate (desde `v2/`): `python -m ruff check eim tests && python -m pytest -q`
- API dev (desde `v2/`): `python -m uvicorn eim.api.main:app --port 8000 --reload`
- Web dev: `cd v2/eim/web && npm run dev`
- Navegador integrado: usar `http://127.0.0.1:PUERTO` (con `localhost` falla).
- Operación en papel (desde `v2/`): `python -m eim.operation run --execution paper` · copias: `python -m eim.data.backup create|verify|restore|list`.
- API solo local: nunca `--host 0.0.0.0`; todo POST nuevo exige la cabecera `X-EIM-Confirm` (lo comprueba `tests/api/test_security.py`).
