# Muestra etiquetada a mano para T66 (◆)

Aquí van **al menos 40 fotogramas reales** etiquetados por el usuario (o quien él designe). Con
ellos `python -m eim.video.visual eval` mide la lectura visual y escribe
`v2/reports/video_visual_eval.md`. Hasta que estén, el informe dice «muestra insuficiente» y
ningún tipo de observación pasa a T67.

## De dónde salen los fotogramas

Solo de material que la postura de YouTube permite (`v2/docs/SEGURIDAD.md` § «Videos de
YouTube»): videos propios, material aportado por el usuario o con permiso escrito del autor.
Nada se descarga de YouTube.

1. `python -m eim.video.visual frames RUTA_DEL_VIDEO --video-id ID` (desde `v2/`) guarda las
   miniaturas elegidas en `data/video/frames/ID/`.
2. `python -m eim.video.visual label-template --video-id ID` copia aquí cada miniatura (`.jpg`)
   con su etiqueta vacía (`.json`).
3. Se abre cada imagen y se rellena su `.json` a mano con lo que **se ve**, sin mirar lo que lee
   el sistema.

Las imágenes son de uso personal: si un video no es del usuario, sus miniaturas no se suben a git
(basta con dejar fuera los `.jpg`; el `.json` sí puede viajar).

## Formato de cada etiqueta (`<frame>.json`)

```json
{
  "frame_id": "ID@000012000",
  "image": "ID_000012000.jpg",
  "video_id": "ID",
  "t": 12.0,
  "published": "2026-11-20T14:00",
  "is_chart": true,
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "observations": [
    {"kind": "nivel", "value": 64250, "unit": "precio"},
    {"kind": "cifra", "value": 3.5, "unit": "%"},
    {"kind": "indicador", "value": 62.3, "unit": "rsi:14"},
    {"kind": "titular", "value": "Bitcoin rompe la resistencia"},
    {"kind": "dibujo", "value": "línea de tendencia"}
  ]
}
```

- `published`: fecha y hora UTC del video (la validación usa las velas reales de esa fecha).
- `kind` ∈ `cifra`, `titular`, `nivel`, `indicador`, `dibujo`. Cifras con su unidad (`USD`, `%`,
  `precio`); indicadores como `rsi:14`, `ema:200`, `sma:50`, `vwap`.
- Solo lo legible en la imagen. Lo que no se ve no se escribe; las marcas del eje de precios no
  se etiquetan (no son cifras de interés).
- `symbol` y `timeframe` en `null` si no se leen en el fotograma.
