"""Lectura visual de video (T66): fotogramas, OCR, visión clásica, modelo visual y validación.

Puro salvo los motores inyectados (`LocalAI.ocr` / `LocalAI.vision`) y el proveedor de velas: el
I/O (leer el video, guardar miniaturas, la tabla `video_observations`) vive en `eim.data.video`.
Lo que no se lee queda `null`; ningún campo sin caja o cita; ninguna cifra se acepta solo por la
imagen (`validate.py`). Fuera de alcance: señales de trading, personas o rostros.
"""
