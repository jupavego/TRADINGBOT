"""Examen físico de los prospectos de la cantera sobre la historia (T169). **Sin rendimiento.**

La historia no asciende a nadie (nota de T167 §3, regla 5): aquí solo se comprueba que un
prospecto **puede** llegar a un veredicto. Que opere lo bastante en la unidad de su banda, que el
costo en R no lo condene de antemano y que no mire el futuro. Ningún módulo de este paquete calcula
ni muestra R neto, acierto o PF, y `tests/nursery/test_exam_no_performance.py` lo vigila.

- `plan`: tramos y agentes, congelados en `plan.json` antes de correr (ficha T169).
- `gen`: contextos ligeros con `nat`, vela a vela y reanudables (I/O).
- `physical`: la física de cada prospecto con el motor de T168 (puro).
- `verdict`: umbrales de la ficha, bandas, descartes y días hasta el veredicto (puro).
- `checks`: no anticipación por truncado e identidad del subconjunto de agentes (I/O).
- `report`: informe Markdown + JSON, con la guarda de columnas prohibidas (puro).
"""
