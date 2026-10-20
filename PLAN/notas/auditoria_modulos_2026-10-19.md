# Auditoría de las 5 esferas «sin datos» — traspaso (2026-10-19)

PR: https://github.com/jupavego/TRADINGBOT/pull/111 (rama `claude/audit-skills-modules-7132dc`).
Skill propia para repetir el diagnóstico: `.claude/skills/eim-diagnose-agent`.

## Estado por módulo
| Módulo | Causa de «sin datos» | Hecho | Falta |
|---|---|---|---|
| Liquidaciones | Dataset de Binance retirado (oct-2024) y `snapshot.liquidations` nunca se llenaba | Recolector en vivo `data/collectors/liq_ws.py` (Binance, Bybit, OKX), `liq_flow`, agente v2 (cascada activa/agotada) | ≥ 24 h de captura y ver la esfera; peso por la puerta T49. **Bybit y OKX verificados con eventos reales (2026-10-19, ~25 min: 5 y 11 eventos; OKX `sz` × 0,01 BTC correcto; OKX usa precio de quiebra `bkPx`, difiere ~0,3 % del de ejecución, no afecta al agregado por vela)** |
| Derivados | El ciclo nunca llamaba a `sync_derivatives` | Ciclo sincroniza funding/OI/long-short/basis cada ≥ 10 min; agente `ok` con datos reales | Verlo en la esfera con el servicio corriendo |
| Contexto | Titulares no llegaban al snapshot y `ContextAgent()` sin analizador | Titulares RSS desde disco; LLM local (Ollama `qwen3:4b`) o Claude por opt-in; segundo plano + caché | Calidad: a veces `degraded` (sin catalizadores con fuente); medir contra Claude (T71) |
| Microestructura (T104 ◐) | El recolector no estaba en el arranque continuo | `servicio_continuo.ps1` lo lanza; la esfera dice apagado/acumulando/sin datos | Diagnóstico escrito, supervisor con latido/reinicio, disco, ≥ 24 h, línea base (ver `PLAN/T104.md`) |
| Smart money | 0 líderes en la base; el scorecard exige ≥ 30 ops y ≥ 7 d | `discover --source ranking` (leaderboard público NO oficial, opt-in); 10 líderes en seguimiento | Esperar ≥ 7 d; 0 aprobados hoy; relanzar el vigilante desde `v2` principal tras fusionar |

## Al retomar
1. Fusionar el PR #111; luego relanzar los servicios desde el checkout principal: `powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1` (arranca vigilante, líderes, micro, liquidaciones y Ollama sin duplicar). Hoy el vigilante de líderes corre desde el worktree de esta rama.
2. Ver las 5 esferas en la UI tras ≥ 24 h (captura de pantalla).
3. Siguientes: completar T104; evaluar el LLM local (T71).

## Advertencias
- El disco E: se desconectó varias veces; si Bash/PowerShell no arrancan, revisar cable/puerto. Tras una caída: comprobar `git status`, `git log` y borrar `.ruff_cache` (ruff entra en pánico con la caché dañada; usar `--no-cache`).
- La suite completa tarda > 25 min con Ollama y los recolectores activos; para el día a día correr solo los tests de la zona.
- Ollama vive en `E:\Ollama` (instalador oficial firmado; modelo `qwen3:4b`, Apache-2.0); `EIM_CONTEXT_LLM=local` lo activa.
