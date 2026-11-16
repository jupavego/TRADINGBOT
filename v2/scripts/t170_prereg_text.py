"""Texto fijo del pre-registro `cantera_v1` (T170), para `t170_prereg.py build`. No calcula."""

from __future__ import annotations


def document(fam: dict, lad: dict, cal: dict, np_, criteria_sha: str, reserve: int,
             ceiling: int, redesigned: tuple[str, ...], not_before: str) -> dict:
    members = fam["members"]
    m = len(members) + reserve
    fp = cal["false_promises"]
    agents = sorted({x["agent_id"] for x in members})
    return {
        "version": "prereg_cantera_v1",
        "declared": "2026-11-16",
        "description": (
            "Pre-registro de la cantera (fase 27, T170): familia, cuentas, controles, medida, "
            "escalafón con todos sus umbrales, plazas de reserva y reloj, fijados ANTES de la "
            "primera operación hacia adelante. Nada de esto se calculó mirando rendimiento: la "
            "historia solo sirvió para el examen físico (T169 y el re-examen de T170). Cambiar "
            "cualquier valor es cantera_v2, con reloj nuevo y sin recalcular el pasado."),
        "mode": "SIMULADO",
        "symbol": "BTCUSDT",
        "criteria": "validation_v1",
        "criteria_sha256": criteria_sha,
        "decisions": [
            "◆ T167 (2026-11-11): 43 prospectos de 13 agentes y techo de la familia 50 = 43 + 7 "
            "plazas de reserva («ampliemos a 40 a 50», «Apruebo»).",
            "Decisión del usuario (2026-11-11): veredictos muy sensibles, dos capas (escalafón "
            "interno con q = 0,10; StepM estricto en la puerta a primer equipo y en todo lo que "
            "toque dinero), sin puerta de potencia y con el precio declarado. Este pre-registro "
            "no endurece el escalafón interno.",
            "◆ T170 (2026-11-16) 1: se rediseñan estructura_ruptura (sin filtro de convicción) y "
            "tec_acuerdo_marcos (marcos de 1 h y 4 h), re-examinadas con la ficha de T169 "
            "(`reports/t170_reexamen.md`); las dos de elliott, de baja.",
            "◆ T170 (2026-11-16) 2: regimen_tramo y regimen_tramo_estable (gemelos físicos) "
            "cuentan como dos prospectos dados de baja.",
            "◆ T170 (2026-11-16) 3: manda la banda medida por la tenencia; las plantillas de "
            "salida no cambian.",
            "◆ T170 (2026-11-16) 4: familia propia (precedente de T160; los datos son nuevos), "
            "con m de e-BH = los que entran + las 7 plazas de reserva.",
        ],
        "family": {
            "kind": "propia",
            "why": (
                "Las operaciones de la cantera son todas posteriores a este pre-registro: datos "
                "nuevos, no la historia ya mirada de las 841 claves de T49/T137/T139. Sumarla a "
                "esa familia haría imposible graduar a nadie con la potencia disponible."),
            "enrolled_t167": len(members) + len(fam["discarded"]),
            "reserve_slots": reserve,
            "ceiling": ceiling,
            "m": m,
            "m_rule": (
                f"e-BH corrige sobre m = {len(members)} que entran + {reserve} plazas de reserva "
                f"= {m}, fijo durante toda la fase. Una baja hacia adelante sigue contando (su "
                "e-valor pasa a 0); una plaza de reserva vacía cuenta con e = 0; una reentrada "
                "ocupa una plaza ya contada. Los descartados por el examen físico no cuentan: "
                "nunca se mide su rendimiento, así que no son hipótesis probadas."),
            "members": members,
            "discarded": fam["discarded"],
            "redesigned": list(redesigned),
        },
        "accounts": {
            "initial_equity_usdt": np_.initial_equity,
            "risk_pct": np_.risk_pct,
            "cost_gate_max_r": np_.tf_max_cost_r,
            "twins_k": np_.twins_k,
            "seed": np_.seed,
            "execution": (
                "La de la corrida aparte T143 (◆ 2026-11-10) con solo lo de AUTO_ADAPT: puerta "
                "de costo por marco (a 0,3 R, el V6 de T49, para no cerrar el scalping antes de "
                "medirlo), entrada maker en 1 h y 4 h y riesgo con costos. Una posición a la vez "
                "por cuenta, mismo capital, mismo riesgo y mismos costos para todas."),
            "not_adapted": (
                "Fijos y comprobados al construir (`nursery/params.py`): peso aprendido de la "
                "escalera = 1, sin freno propio (lo sustituye el tope de drawdown) y salida "
                "adaptativa apagada."),
        },
        "controls": [
            f"Gemelos aleatorios pareados: por cada operación, K = {np_.twins_k} entradas de lado "
            "al azar en la misma vela, con la misma plantilla, los mismos costos y salida como "
            "mucho cuando sale la real; d = R − media de los gemelos.",
            "Comprar y mantener desde el alta, en % y en unidades de riesgo (1 R = 1,5 ATR del "
            "primer cierre), con desglose largo/corto.",
            "El agente_{id} genérico (sigue al agente si |sesgo| ≥ 0,3 y confianza ≥ 20 %, "
            "plantilla atr_ladder), uno por agente y marco con prospectos. Los controles no "
            "cuentan en la familia.",
        ],
        "measure": {
            "principal": "Rentabilidad neta acumulada de la cuenta propia (%), con comisiones, "
                         "deslizamiento y funding.",
            "primary_hypothesis": (
                "Una por prospecto: H0 E[d̃] ≤ 0, con d̃ = recorte de d a ±3 R. e-proceso mezcla "
                "por apuestas sobre y = d̃/3 (rejilla λ = 0,1…0,9). Solo cuentan las operaciones "
                "contabilizadas y cerradas en exit_t ≤ t; las sombras de la puerta de costo, no."),
            "secondary": [
                "Nativo frente a genérico, una por agente: d de sus prospectos frente al del "
                f"agente_{{id}} genérico, Holm sobre los {len(agents)} agentes con prospectos "
                "(α = 0,10, capa sensible).",
                "Por tema (tendencia, reversión, derivados, consenso): media de efectos "
                "aleatorios > 0, Holm sobre los 4 temas (α = 0,10). Estimaciones encogidas "
                "hacia el tema (DerSimonian-Laird) en el panel y en T172.",
                "Hermano simple: requisito de Promesa para los complejos (a empate, el simple).",
                "Comprar y mantener: descriptivo.",
                "SPA de T161 sobre la familia: solo prueba de humo. PBO/CSCV: descriptivo.",
            ],
            "unit": "R por operación dentro; rentabilidad % hacia fuera.",
        },
        "bands": {
            "scalping": "operación", "intradia": "operación", "tres_dias": "operación",
            "semanal": "día (suma diaria de d; los días sin cierre no mueven el e-proceso)",
            "rule": (
                "Manda la banda medida por la tenencia mediana (T169; T170 para las dos "
                "rediseñadas). Los 11 sin historia usan su banda declarada hasta su examen "
                "físico hacia adelante, al salir de guardería, que la mide con la misma ficha y "
                "la congela."),
            "templates": (
                "Plantillas de salida sin cambio (◆ 2026-11-16): atr_ladder en 1 h cierra en "
                "1–4 h y rule_flip en 4 h en 4–62 h; los 5 descartes que dependían de la "
                "reasignación se mantienen."),
            "cost_gate": (
                "Puerta de costo de la cantera: 0,3 R (V6 de T49), la misma vara del examen "
                "físico, automática por marco con todas sus cuentas (AUTO_ADAPT)."),
        },
        "ladder": lad,
        "false_promises": {
            **fp,
            "power": cal["power"],
            "reading": (
                f"Bajo la nula global, el paso por e-BH deja de media {fp['mean']} promesas "
                f"falsas en la fase (P(≥ 1) = {fp['p_at_least_one']}); los demás requisitos "
                "solo pueden quitar ascensos. e-BH garantiza FDR ≤ 0,10 bajo cualquier "
                "dependencia, y en la práctica es más estricto: el precio es la potencia "
                "(tabla `power`, ascenso en solitario con e ≥ m/q)."),
        },
        "reserve": [
            f"{reserve} plazas de reserva del techo de {ceiling}: solo para reentradas (versión "
            "nueva de un prospecto dado de baja, también de los descartados por el examen "
            "físico) o para los prospectos en reserva de T167 si vuelven sus datos.",
            "Como mucho una reentrada por prospecto dado de baja.",
            "Causa nombrada (variable sin información, costo, cadencia o la teoría contraria) e "
            "hipótesis escrita con su obra del catálogo; «perdió dinero» no basta.",
            "◆ del usuario para cada reentrada, que se anota antes de su primera operación en un "
            "anexo de solo adición, con su huella; no cambia nada más de cantera_v1.",
            "Solo si su MinTRL (T161) con +0,25 R cabe en los días que le quedan a la fase.",
            "Prospecto nuevo: huella nueva, cuenta nueva desde el capital inicial y en "
            "guardería, sin heredar operaciones; su guardería e inactividad cuentan desde su "
            "alta, y sigue el calendario de revisiones de la fase.",
        ],
        "clock": {
            "not_before_utc": not_before,
            "alta": (
                "El primer cálculo de la cantera con EIM_NURSERY=1 posterior a not_before y al "
                "commit de este archivo, anotado en `paper_cantera.duckdb` (tabla "
                "nursery_prereg) con la versión y la huella; ninguna operación anterior cuenta."),
            "reviews": (
                "Revisiones fijas a los días 30, 61, 91, 121, 152 y 182 desde el alta. Solo en "
                "ellas cambia una etapa; la lectura semanal de T159 y el panel no son miradas."),
            "deadline": (
                "Día 182 (6 meses): mirada final. Las promesas que cumplen el primer equipo "
                "quedan como candidatas (◆ T172: el usuario confirma o veta la salida mecánica, "
                "no elige entre candidatos); el resto, baja por fecha límite."),
            "stop_rule": (
                "La fase termina en la fecha límite aunque nadie llegue a primer equipo, que es "
                "el resultado más probable y también informativo. Graduarse no habilita dinero: "
                "permite, con ◆, inscribir el perfil en T49; la decisión D (T145) sigue."),
            "change_rule": (
                "Un cambio de fórmula, umbral, familia o cuentas a mitad de fase solo puede ser "
                "cantera_v2, con pre-registro y reloj nuevos y sin recalcular ni reinterpretar lo "
                "de v1."),
        },
        "self_improvement": [
            "Solo se adapta solo lo de AUTO_ADAPT (costo y riesgo); reglas, parámetros, "
            "plantillas, escalafón, techo, capital y riesgo base nunca cambian solos.",
            "Los días con el marco cerrado por la puerta de costo no cuentan para la baja por "
            "inactividad ni para la cadencia del examen hacia adelante.",
            "Las variantes de ejecución (§9.3) no suman intentos ni tocan el libro de la "
            "cantera; adoptarlas exige resultado medido y ◆, y se aplican a todas las cuentas.",
            "La lectura semanal de T159 describe y no es una mirada del método secuencial.",
            "Cada adaptación es un evento del libro con hora, marco, valor, umbral y cuentas.",
        ],
        "notes": [
            "Promesa: los requisitos no estadísticos se miran antes de e-BH (quien no los cumple "
            "entra con e = 0) y el e-valor de quien asciende queda congelado; así todo ascenso "
            "de la fase pertenece al e-BH sobre e-valores detenidos y la FDR sigue ≤ q.",
            "Futilidad: cota superior unilateral de E[d̃] con z = z(1 − 0,10/6) (Bonferroni "
            "sobre las 6 revisiones) < +0,10 R, con n ≥ 30: probabilidad de una baja injusta "
            "≤ 0,10 para un prospecto con E[d̃] ≥ +0,10 R, sea cual sea su ritmo.",
            "Tope de drawdown: cuantil 95 % del drawdown máximo realizado con +0,25 R por "
            "operación, σ = 1,3 R (el extremo alto de lo razonable, T139 §4), riesgo 1 % y las "
            "operaciones esperadas en 6 meses (T169; 1 000 sin historia).",
            "Claramente negativo al salir de guardería: media de d̃ + 1·EE < 0 con n ≥ 30 "
            "(regla de T49, sobre d y no sobre R neto).",
            "Contribución marginal: correlación del P&L diario > 0,7 con el hermano o el "
            "genérico exige aportar por encima (media diaria de la diferencia > 0).",
            "Persistencia del orden: en los meses 1–3 y 4–6, media de d > 0 y por encima de la "
            "mediana de la familia (≥ 10 operaciones en cada mitad).",
        ],
    }
