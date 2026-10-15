# Guía de operación

Todo se ejecuta desde `v2/` con el entorno virtual activo. Instalación desde cero: `ONBOARDING.md`
(raíz del repositorio). Incidentes: `docs/RUNBOOK.md`. Seguridad: `docs/SEGURIDAD.md`.

## 1. Levantar el sistema (de cero a funcionando)
```bash
cd v2
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ruff check eim tests && python -m pytest -q   # gate: debe pasar
cd eim/web && npm install && cd ../..
```
Entorno idéntico al probado: `python -m pip install -r requirements-lock.txt && python -m pip install -e . --no-deps`.

| Qué | Comando (desde `v2/`) | Notas |
|---|---|---|
| Solo análisis (API + UI) | `python -m uvicorn eim.api.main:app --port 8000` y `cd eim/web && npm run dev` | UI en `http://127.0.0.1:5173` |
| Operación en papel (servicio continuo) | `python -m eim.operation run --execution paper` | API + ciclo + vigilante que relanza el proceso; copia diaria automática |
| Operación en testnet | `EIM_TESTNET_API_KEY=… EIM_TESTNET_API_SECRET=… python -m eim.operation run --execution testnet` | Antes: `python -m eim.execution.smoke` (BACKLOG T30/T31) |
| Informe del periodo | `python -m eim.operation report [--from AAAA-MM-DD] [--to AAAA-MM-DD]` | Lo genera la API en marcha |
| Copia de seguridad a demanda | `python -m eim.data.backup create` | Si la API está en marcha, se la pide a ella. La CLI usa `EIM_DATA_DIR`, `EIM_BACKUP_DIR` y `EIM_BACKUP_KEEP` como la API |

**Nunca** lances la API con `--host 0.0.0.0`: además de quedar en la red, el middleware de
`eim/api/security.py` rechazará a los clientes remotos (403) y los `Host` ajenos (400).

## 2. Variables de entorno
| Variable | Defecto | Uso |
|---|---|---|
| `EIM_DATA_DIR` | `data` | Almacén (parquet, DuckDB, estado) |
| `EIM_EXECUTION` | `off` | `paper` / `testnet` |
| `EIM_OPERATE`, `EIM_OPERATE_TF`, `EIM_OPERATE_POLL_S` | `0`, `1h`, `60` | Servicio continuo (lo fija `eim.operation run`) |
| `EIM_BACKUP_DIR`, `EIM_BACKUP_KEEP` | `backups`, `14` | Copias; se conservan las N más recientes |
| `EIM_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` | Cabeceras `Host` aceptadas |
| `EIM_API_TOKEN` | — | Sin él, ningún cliente remoto entra. Con él: `Authorization: Bearer <token>`; en WebSocket, subprotocolo `eim-token.<token>` (los navegadores no admiten cabeceras ahí) |
| `EIM_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Orígenes del navegador (también para el WebSocket) |
| `EIM_TESTNET_API_KEY` / `_SECRET` / `_URL` | — | Solo testnet; el broker bloquea cualquier otro host |
| `EIM_CALENDAR`, `EIM_CALENDAR_S` | `1`, `21600` | Calendario económico (Fed/BLS/BEA): consulta al arrancar y cada 6 h en `data/calendar/` (T36). `0` lo apaga |
| `EIM_ARBITRAGE`, `EIM_ARBITRAGE_S` | `1`, `10` | Escáner de arbitraje Binance (REST público, solo lectura): fotografía cada ~10 s en `data/arbitrage/` (últimas 20), pestaña «Arbitraje» y mensaje WS `arbitrage` (T39). `0` lo apaga. Modo Análisis: no ejecuta |
| `EIM_ARB_ALERT_SCORE`, `EIM_ARB_ALERT_S` | `3`, `60` | Alerta de arbitraje: puntuación del selector ≥ umbral (pb/día ajustados por riesgo) sostenida N segundos de escaneos seguidos (T39) |
| `EIM_FRED_API_KEY` | — | Opcional (gratuita): valores real/anterior/revisado de IPC, NFP, PCE, PIB, IPP desde FRED. Sin ella los eventos salen sin valores |
| `EIM_WS_URL`, `EIM_HEARTBEAT_S`, `EIM_SNAPSHOT_BARS`, `EIM_AUTO_HISTORY`, `EIM_RECON_S` | ver `eim/api/config.py` | |

## 3. Copias de seguridad
Qué se copia (`eim/data/backup.py`): la base `reports.duckdb` (copia consistente), kill-switch, estado y
registros del servicio, versiones de parámetros (`eim/risk/versions`, `eim/calibration/versions`) y un
`manifest.json` con SHA-256 por archivo, filas por tabla y commit de git. Las velas solo con
`--with-market` (se pueden volver a descargar). **Nunca** se copian claves.

- **Automática:** con el servicio de operación, una copia por día UTC en `EIM_BACKUP_DIR`. Si falla,
  alerta `copia_seguridad` (una vez) y se reintenta cada hora (no en cada ciclo: la copia retiene el cerrojo de la base) sin detener la operación.
- **A demanda:** `python -m eim.data.backup create [--with-market]` o `POST /v2/backup` (cabecera `X-EIM-Confirm: backup`). Con el servicio en marcha, la copia espera a que termine el ciclo en curso: base y libro simulado quedan consistentes entre sí.
- **Verificar:** `python -m eim.data.backup verify [carpeta]` (por defecto la última). Hazlo tras cada copia manual.
- **Listar:** `python -m eim.data.backup list`.
- **Restaurar:** ver `docs/RUNBOOK.md` §5.
- **Fuera del equipo:** `backups/` está en `.gitignore` y vive en el mismo disco. Sincroniza esa
  carpeta con otro disco o un almacenamiento en la nube (p. ej. OneDrive) o usa `EIM_BACKUP_DIR`
  apuntando a otra unidad.

## 4. Versionado de parámetros
- Un conjunto de parámetros publicado es **inmutable**: cambiar límites de riesgo = `risk_v2.json`
  nuevo en `eim/risk/versions/` (el campo `version` debe coincidir con el nombre); calibraciones en
  `eim/calibration/versions/` con estado (aceptado/rechazado) y hash de datos.
- `tests/test_param_versions.py` guarda el SHA-256 de cada versión publicada: editar una rompe el gate.
  Al añadir una versión, registra su hash en ese test en el mismo PR.
- Cada `RiskDecision` lleva `config_version` y `config_sha256`; el hash ignora el fin de línea
  (`.gitattributes` fija LF) para que sea igual en todos los equipos.
- Parámetros de agentes (`eim/agents/<id>/params.py`): modelos pydantic con valores por defecto
  versionados con el código; un cambio que altere la salida sube la `version` del agente.

## 5. Dependencias: política de actualización
- **Rangos** en `pyproject.toml` / `package.json`; **versiones probadas** en `requirements-lock.txt` y
  `eim/web/package-lock.json`.
- **Cada mes** (y antes de pasar a testnet o de cualquier cambio de modo):
  ```bash
  python -m pip_audit                    # vulnerabilidades Python (paquete [dev])
  cd eim/web && npm audit                # vulnerabilidades del frontend
  ```
- **Actualizar** en una rama propia (`deps-AAAA-MM`): `python -m pip install -U <paquete>` /
  `npm update`, pasar el gate + `npm run build`, regenerar `requirements-lock.txt`
  (`python -m pip freeze --exclude-editable`, conservando la cabecera) y abrir PR. Nunca mezclar con
  funcionalidad.
- **Mayores** (p. ej. pandas 3→4, Vite 6→7): PR dedicado con nota de cambios; Vite 7+ exige Node ≥ 20.19.
- Vulnerabilidad **alta** en algo que corre en la API → se corrige antes de seguir operando.
- Código de terceros nuevo: licencia y seguridad antes de copiar (ver `PLAN/notas/T04_auditoria.md`).

## 6. Rutina
- **Diario:** pestaña «Operación» de la UI (estado, alertas activas, kill-switch, reconciliación).
- **Semanal (lunes UTC):** leer `reports/operation/semana_AAAA-Www.md` (se genera solo).
- **Mensual:** auditoría de dependencias (§5) y `python -m eim.data.backup verify` sobre una copia
  antigua (prueba de restauración en una carpeta temporal: `restore <copia> --data-dir <tmp>`).
