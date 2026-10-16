"""Bróker simulado (T47): laboratorio de estrategias en papel con 3 perfiles y retroalimentación.

Flujo: contexto compacto por vela (`context`) → ideas de un catálogo amplio de estrategias
(`strategies*`) → ejecución sobre velas de 15 m (`engine`, evaluación «sombra» en R, igual para
todos) → libro por perfil (`book`, en USDT, con tamaño, margen y bitácora) ponderado por lo
aprendido (`feedback`, solo con operaciones ya cerradas: sin mirar el futuro).
Siempre `mode=SIMULADO`: nunca envía órdenes.
"""
