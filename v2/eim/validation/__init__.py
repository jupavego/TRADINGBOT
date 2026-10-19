"""Puerta de validación por estrategia (T49).

¿Qué `estrategia@marco@versión` del bróker simulado tiene evidencia fuera de muestra suficiente,
neta de costos, para alimentar las operaciones sugeridas? Criterios fijados antes de calcular
(`criteria.py` + `versions/`), puerta pura (`gate.py`), registro de intentos y veredictos
(`eim/data/validation_store.py`), recálculo en el servicio del bróker e informe (`__main__`).
«Ninguna validada» es un resultado válido. Siempre SIMULADO.
"""
