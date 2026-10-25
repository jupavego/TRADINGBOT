# T117 — Primera mezcla real de la experiencia compartida

**Estado (2026-10-25): ◐, mitad de este equipo hecha.** El segundo equipo (`jupavego`) todavía no
podía hacer su parte. Lo que falta está en §6, y las instrucciones para reenviarle, en §7.
Hasta que no estén los dos simulacros reales, T61 sigue con su ◆ abierto.

## 1. Decisiones del usuario (2026-10-25)

| Pregunta | Decisión |
|---|---|
| Transporte | **Repo git privado aparte**: `https://github.com/Santivego/eim-shared-data` (creado el 2026-10-25, privado; solo ramas `machine/<id>`, nunca código ni claves). |
| Alias de este equipo | **El id actual `laptop-i6pf9ovp-fce8d9`** (sin `--machine`). Ya sellaba 77 138 filas de `leader_recon` y 5 694 de `leader_gaps`: con otro alias, la procedencia de este equipo quedaría partida en dos. |
| Modo automático | Se activa **solo después de revisar el simulacro** (la API en vivo sigue con `enabled: false`; no hay `data/share_config.json` en la carpeta viva). |
| Segundo colaborador | **Todavía no**: se deja hecha la mitad de este equipo y las instrucciones para él. |

## 2. Lo que destapó el ensayo con datos reales (corregido en esta rama)

1. **Límite de 90 MB del transporte git.** Con la copia de hoy, `leader_fills.parquet` pesa **80,3 MB**
   y crece ~9 MB/día (≈ 200 000 ejecuciones/día). La publicación habría fallado en 1 o 2 días, y
   después cada 6 h, sin solución. → **Formato 2 del manifest**: una tabla de más de 64 MB
   (`PART_BYTES`) viaja en partes `<tabla>.partNNN.parquet` (disjuntas, en orden de clave y cada una con
   su SHA-256). El código anterior la rechaza con «actualiza el código», en vez de importar solo
   una parte. Se siguen leyendo las exportaciones de formato 1.
   Real: `leader_fills` sale en 2 partes de 40 MB.
2. **Importación no idempotente con NULL en la clave.** 1 862 huecos del websocket (`leader_gaps`,
   `cause='ws'`) no tienen símbolo. La clave se comparaba con `=` y NULL nunca casaba: en **cada**
   importación se volvían a insertar (con el modo automático, varias veces al día). → La clave se
   compara con `IS NOT DISTINCT FROM`. Prueba: `tests/share/test_leaders.py::test_gap_without_symbol_is_idempotent`,
   que falla sin el arreglo.
3. **La procedencia inflaba las «duplicadas».** `GET /v2/validation` → `provenance` sumaba
   `n_dup` de todas las importaciones: tras dos importaciones idénticas decía 76 572 contextos
   descartados de una foto de 38 286. → Duplicadas = filas de la **última** foto de esa máquina que ya
   estaban aquí sin haberse importado de ella. Prueba en `tests/share/test_versions.py`.
4. **Rutas largas en Windows.** `git add` falló con «Filename too long» (más de 260 caracteres
   bajo `share_repo/view/<id>/.git/objects/…`). → `core.longpaths=true` en las llamadas del
   transporte. En la carpeta real la ruta mide ~171 caracteres, pero la del otro equipo puede ser más larga.

## 3. Ensayo local con datos reales (NO es la mezcla real)

Dos «equipos» hechos con copias de **este** historial, en un directorio temporal y sin tocar las
bases vivas: **A** = copia diaria del 2026-10-25 00:00 UTC (`laptop-i6pf9ovp-fce8d9`); **B** = copia
de T115 del 2026-10-24 16:17 UTC con id `ensayo-b`. Como B es un subconjunto anterior de A, el
ensayo es justo el caso «el otro equipo corrió la misma `estrategia@marco@versión`».

Simulacro y aplicación dan el mismo informe. Así quedó tras los arreglos de §2:

```
IMPORTACIÓN APLICADA · 20261025T174338Z-laptop-i6pf9ovp-fce8d9 · destino: laptop-i6pf9ovp-fce8d9 · modo SIMULADO
tabla             origen                  nuevas  ya estaban  conflicto  incompat.
reports           ensayo-b                     0       11194          0          0
sim_trades        ensayo-b                     0          40          0          0
paper_ctx         ensayo-b                     0       38286          0          0
val_versions      ensayo-b                     0         191          0          0
val_windows       ensayo-b                     0         191          0          0
leaders           ensayo-b                     0          15          0          0
leader_fills      ensayo-b                     0     1693902          0          0
leader_funding    ensayo-b                     0       23032          0          0
leader_leverage   ensayo-b                     0           3          0          0
leader_positions  ensayo-b                     0       28298          0          0
leader_follow     ensayo-b                     0     1422091          0          0
leader_recon      ensayo-b                     0       74061          0          0
leader_gaps       ensayo-b                     0        5211          0          0
copy_journal      ensayo-b                     0       12403          0          0
veredictos recalculados BTCUSDT: 191 intentos registrados
```

```
IMPORTACIÓN APLICADA · 20261025T174449Z-ensayo-b · destino: ensayo-b · modo SIMULADO
tabla             origen                  nuevas  ya estaban  conflicto  incompat.
reports           laptop-i6pf9ovp-fce8d9       456       11194          0          0
sim_trades        laptop-i6pf9ovp-fce8d9         0          40          0          0
paper_ctx         laptop-i6pf9ovp-fce8d9        41       38286          0          0
val_versions      laptop-i6pf9ovp-fce8d9         0         191          0          0
val_windows       laptop-i6pf9ovp-fce8d9         0         191          0          0
leaders           laptop-i6pf9ovp-fce8d9         0          15          0          0
leader_fills      laptop-i6pf9ovp-fce8d9     66753     1693902          0          0
leader_funding    laptop-i6pf9ovp-fce8d9       721       23032          0          0
leader_leverage   laptop-i6pf9ovp-fce8d9         0           3          0          0
leader_positions  laptop-i6pf9ovp-fce8d9      1348       28298          0          0
leader_follow     laptop-i6pf9ovp-fce8d9     64221     1422091          0          0
leader_recon      laptop-i6pf9ovp-fce8d9      3077       74061          0          0
leader_gaps       laptop-i6pf9ovp-fce8d9       483        5211          0          0
copy_journal      laptop-i6pf9ovp-fce8d9       433       12403          0          0
veredictos recalculados BTCUSDT: 191 intentos registrados
```

(Antes del arreglo 2, el simulacro de B daba `leader_gaps` 2 184 nuevas y el de A, 1 701 «nuevas»
procedentes de una copia **más antigua** del mismo equipo: así salió el fallo.)

**Cifras antes/después** (A y B; sin conflictos ni incompatibles):

| | A antes | B antes | A después | B después |
|---|---|---|---|---|
| `val_versions` (intentos de la puerta T49) | 191 | 191 | **191** | **191** |
| estrategia@marco distintas | 104 | 104 | 104 | 104 |
| `val_windows` | 191 | 191 | 191 | 191 |
| `paper_ctx` | 38 327 | 38 286 | 38 327 | 38 327 |
| `reports` | 11 650 | 11 194 | 11 650 | 11 650 |
| `leader_fills` | 1 760 655 | 1 693 902 | 1 760 655 | 1 760 655 |
| `leader_gaps` | 5 694 | 5 211 | 5 694 | 5 694 |
| `leader_recon` | 77 138 | 74 061 | 77 138 | 77 138 |

- **Unión, no suma:** `n` no crece. Las 191 versiones de B tienen las mismas huellas y salen «ya
  estaban», y Holm sigue contando 191 intentos. Los 41 contextos nuevos de B son velas que A tenía y B no:
  amplían la cobertura en tiempo, no cuentan como intentos.
- **Conmutativa:** tras mezclar en los dos sentidos, A y B quedan idénticos en todas las tablas.
- **Idempotente:** repetir la aplicación en A y en B no cambia ninguna cifra (todo «ya estaban»).
- **Copia previa:** cada aplicación dejó su `pre-import_<id>` (las bases completas).
- **Procedencia** (con el arreglo 3, tras dos importaciones): en B,
  `paper_ctx` 41 importadas / 38 286 duplicadas y `val_versions` 0 / 191. En A, `paper_ctx`
  0 / 38 286 y `val_versions` 0 / 191.

**Tiempos** (equipo cargado por los servicios en vivo): exportar 14–15 s, simulacro 24–33 s y
aplicar 50–69 s (incluye la copia previa de ~630 MB y el recálculo). Bajo el cerrojo, lo que esperan
los escritores dentro de los servicios en modo automático: `reports` 0,3–2,2 s, `paper` 0,6–0,8 s y
**`leaders` ~10 s aunque no llegue nada nuevo y ~32 s con 137 000 filas nuevas**. El bucle del servicio
de líderes sigue (la unión corre en un hilo), pero su captura espera para escribir. Por eso, si el
otro equipo trae mucho historial de líderes, conviene hacer la **primera** mezcla a mano (ver §6).

## 4. Este equipo publicado

- Rama `machine/laptop-i6pf9ovp-fce8d9`, commit `988370e`, exportación `20261025T175246Z`, hecha
  desde la copia diaria del 2026-10-25 00:00 UTC. Así se publicó sin tocar la API ni el servicio de
  líderes en vivo, y la primera exportación automática la reemplazará. 14 tablas y 3 451 889 filas, ~160 MB.
  Exportar y subir llevó 183 s.
- **Comprobada la ida y vuelta**: un tercer equipo de ensayo (`ensayo-c`, vacío y solo de lectura:
  no publicó rama) clonó el repo, verificó el SHA-256 de cada parte y su simulacro trajo las 3 451 889
  filas como nuevas, sin rechazos, en 103 s. Es lo que verá el colaborador en su primer simulacro,
  salvo lo que él ya tenga.
- `git ls-remote` del repo: solo existe esa rama.

## 5. Línea base de la evidencia en vivo (antes de la mezcla real)

`GET /v2/validation` de la API en vivo, asof 2026-10-25 16:00 UTC: **191 intentos**, 104 veredictos
(99 EN OBSERVACIÓN, 5 RECHAZADA), `provenance` **vacío** (nunca se importó nada). Cobertura: 38 246
contextos (backtest 37 404, vivo 842), 354 809 ideas y 62 378 operaciones simuladas.
`GET /v2/share/status` → `{"mode":"SIMULADO","enabled":false}`.

## 6. Lo que falta para cerrar T117 (y el ◆ de T61)

1. **Fusionar esta rama y desplegarla** en la API y en el servicio de líderes de los **dos** equipos,
   antes de cualquier mezcla real. El código de `main` anterior no lee las partes y reinserta los huecos
   sin símbolo.
2. ~~**Dar acceso de escritura** a `jupavego` en `Santivego/eim-shared-data`~~ → invitación enviada
   el 2026-10-25 20:14 UTC con permiso `write`, a la espera de que la acepte
   (`gh api repos/Santivego/eim-shared-data/invitations`; caduca a los 7 días si no la acepta).
3. **Colaborador**: instrucciones de §7 (alias distinto, `setup` y `export`, y su simulacro de lo nuestro).
   Comprobar en `git ls-remote` que su rama se llama distinto de `machine/laptop-i6pf9ovp-fce8d9`.
4. **Este equipo, simulacro real**: `python -m eim.data.backup create` (en caliente), copiar las tres
   bases y `machine_id` de esa copia a una carpeta de trabajo con `share_config.json`
   (`setup --data-dir <trabajo> --git-url …`) y `python -m eim.data.share import --data-dir <trabajo>`.
   Pegar aquí los dos informes tal cual (el nuestro y el suyo).
5. **◆ del usuario**: revisa los dos simulacros y anota aquí su visto bueno con fecha.
6. **Aplicar**. Si el colaborador trae poco historial de líderes: `setup --git-url …` en la carpeta viva
   (sin `--machine`) y reiniciar la API y los líderes; el modo automático aplica con copia previa en ≤ 2 min.
   Si trae mucho (más de ~100 000 filas de líderes): primero a mano, con los vigilantes y servicios
   detenidos (`import --apply`), y luego el `setup` y el arranque. En los dos casos: `share_conflicts`
   fila a fila, `provenance` frente a lo esperado y evidencia antes/después frente a §5.
7. **Modo automático en vivo**: `GET /v2/share/status` con `last_import`/`last_export` avanzando solos
   en los dos equipos. **Fallo provocado** con git (equivalente a «carpeta sin sincronizar»): borrar
   una parte en `data/share_repo/view/<otro>/…`. La importación se rechaza («falta …»), se anota en
   `error` y se reintenta en 10 min sin tocar la operación. Ojo: no se repara sola mientras el otro no
   publique una foto nueva (BACKLOG T117 (3)); para repararla, `git -C … reset --hard`.
8. **Idempotencia en vivo**: repetir el simulacro sobre una copia nueva. Todo debe salir «ya estaban».

## 7. Instrucciones para el segundo colaborador (para reenviar)

> 1. Actualiza el código con el script de `v2/docs/RETOMAR_COLABORADOR.md` (respaldo, `git pull`,
>    reinstalar, gate), cuando la rama de T117 esté en `main`.
> 2. Acepta la invitación de GitHub a `Santivego/eim-shared-data` (repo privado, solo datos).
> 3. Elige un alias **tuyo** (p. ej. `juan-portatil`), que no sea `laptop-i6pf9ovp-fce8d9`. Ese es el
>    otro equipo, y nunca debes cambiar el tuyo después.
>    Comprueba que no exista ya: `git ls-remote https://github.com/Santivego/eim-shared-data.git`.
> 4. Desde `v2/`, **con la API y el servicio de líderes detenidos** (y sin arrancarlos hasta el paso 6):
>    ```powershell
>    python -m eim.data.share setup --git-url https://github.com/Santivego/eim-shared-data.git --machine <tu-alias>
>    python -m eim.data.share export      # publica tu rama machine/<tu-alias>
>    python -m eim.data.share import      # SIMULACRO: qué traería de laptop-i6pf9ovp-fce8d9
>    ```
>    No ejecutes `import --apply` todavía. Copia la salida completa del simulacro y envíasela a Santivego.
> 5. Si tu rama no se publicó («error: …»), envía también ese mensaje.
> 6. Cuando Santivego revise los dos simulacros, aplicad cada uno (`import --apply`) y arrancad los
>    servicios: desde entonces importan y exportan solos.
