"""Modo de operación: toda vista de plan/operación debe mostrarlo."""

from enum import StrEnum


class Mode(StrEnum):
    ANALISIS = "ANALISIS"
    SIMULADO = "SIMULADO"
    TESTNET = "TESTNET"
    REAL = "REAL"
