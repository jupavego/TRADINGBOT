# T128 — la base de líderes seguía creciendo: poda por fecha y compactado en marcha

2026-11-10. Revisión de la semana de medición (2026-11-02 23:13 → 2026-11-09 23:13 UTC) y arreglo.

## 1. Lo medido: la base no estaba acotada

Con las copias de cada noche (compactas, así que miden solo datos) y `pragma_database_size`:

| Copia | 3-nov | 4-nov | 5-nov | 6-nov | 7-nov | 8-nov | 9-nov | 10-nov |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Datos (MB) | 1 172 | 1 238 | 1 343 | 1 474 | 1 573 | 1 619 | 1 689 | 1 781 |

- +609 MB en 7 días (≈ 87 MB/día), en línea recta. Antes de T128 eran ≈ 300 MB/día.
- **Todo el crecimiento era de los 22 líderes rechazados**, los que debían quedarse con 7 días:
  `leader_fills` de 2,55 a 4,54 M filas y `leader_follow` de 1,90 a 3,91 M; en la copia del
  10-nov seguía habiendo detalle del 29-oct (y alguna fila de febrero).
- **Causa:** la poda solo cortaba donde la posición del líder quedaba plana
  (`trip_archive._flat`). Un líder que siempre tiene algo abierto no se podaba nunca. La poda
  diaria sí corría (84 k, 47 k y 27 k ejecuciones del 7 al 9-nov) frente a 140–270 k nuevas al día.
- El archivo vivo pesaba 2 764 MB frente a 1 781 de datos: solo se compactaba al arrancar el
  vigilante, y el último compactado registrado era del 5-nov.
- `leader_recon` ocupa 6 MB: no necesita retención. `leader_positions` (93 MB, ≈ 5 MB/día)
  alimenta la cobertura de la evaluación (`photo_times`) y la copia simulada; se deja entera
  (BACKLOG T128 (1)).

## 2. El arreglo

1. **Corte por fecha con la posición abierta** (`eim/copytrading/trip_archive.py`,
   `trip_fold.py`): se corta en el último instante ≤ ahora − 7 días sin patas a la espera de
   cotización, con la posición abierta o no. El viaje abierto se archiva ya plegado
   (`SymbolBase.open`, sin patas: su estado son cifras) y la evaluación lo sigue desde ahí.
   En la base va como fila `seq = -1` de `leader_archive_trips`, reescrita en cada poda: no
   cambia el esquema y los archivos de antes siguen valiendo (`eim/data/leader_archive.py`).
   La marca del viaje abierto en cada posible corte no copia sus deslizamientos (solo su
   longitud): copiarlos en cada grupo sería cuadrático con un viaje de miles de patas.
2. **Compactado con el servicio en marcha** (`leader_service.py`, `cli.py`, `watchdog.py`): tras
   la poda diaria, si más del 30 % de la base está libre (las mismas reglas que `compact`), el
   servicio para su bucle y sale con `COMPACT_EXIT` (75). El vigilante lo trata como reinicio
   planificado: no cuenta como caída, no avisa ni espera, compacta y relanza. Un fallo del
   compactado se registra y el servicio vuelve igual.

## 3. Medido sobre una copia de la base real

Copia de la noche del 10-nov, por la cola (`t128-poda-copia`, 8 min, sin pausas):

- Ejecuciones: 4 540 936 → **2 399 373**; 81 viajes abiertos archivados; el detalle de los
  rechazados empieza el **2026-11-02** (7 días). El que más bajó: 1,79 M ejecuciones y 1,46 M
  cotizaciones de un solo líder de alta frecuencia.
- **Tablero idéntico** antes y después de podar (comparado entero, en JSON con claves ordenadas).
- Poda: 266 s la primera vez (en el servicio corre en su hilo, a nivel batch).
- Compactada: 2 233 → **1 205 MB** (la copia original, 1 781 MB). Sin poda nueva, lo que queda
  es una ventana de 7 días que se desplaza.

## 4. Lo que falta para cerrar T128

- Desplegarlo: hace falta reiniciar el servicio de líderes (~5 min sin capturar líderes; no
  toca la captura HFT). La primera poda corre a los 30 min del arranque y, si deja más del 30 %
  libre, el servicio sale a compactar solo.
- Medir otra semana que la base deja de crecer.
- La CPU en reposo del EIM: el informe W45 da 13–14 % de media diaria con todo en marcha, que no
  es la CPU en reposo de T126; hay que acordar con qué vara se compara (BACKLOG T128 (2)).
