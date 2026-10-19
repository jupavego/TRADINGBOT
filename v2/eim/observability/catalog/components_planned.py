"""Catálogo: módulos PLANEADOS (aún sin código). Entran como punteado en el mapa (T75).

Cada fila apunta a su tarea en `PLAN/STATUS.md`; un test exige que esa tarea no esté hecha.
Al construirlos, la misma tarea cambia `built` a «construido» y declara la instrumentación.
"""

from __future__ import annotations

from eim.observability.catalog.model import Component, c

_P = {"built": "planeado"}

PLANNED: tuple[Component, ...] = (
    c("leaders.copy_testnet", "leaders", "ejecucion", "service", "leaders", "T46",
      "Copia en testnet", "Replicará a los líderes aprobados en la testnet con un asignador de "
      "capital y la puerta de riesgo. Aún no existe.", consumes=(("leaders.copy_sim", "copy_trade"),),
      produces=("fill",), **_P),
    c("validation.setups_publisher", "validation", "validacion", "service", "api", "T50",
      "Publicador de sugerencias", "Publicará solo las sugerencias de estrategias que pasaron la "
      "puerta de validación, con su evidencia. Aún no existe.",
      consumes=(("validation.gate", "validation_verdict"),), produces=("setup",), **_P),
    c("validation.setups_followup", "validation", "validacion", "service", "api", "T51",
      "Seguimiento de sugerencias", "Seguirá cada sugerencia publicada hasta su resultado y "
      "alimentará la mejora. Aún no existe.",
      consumes=(("validation.setups_publisher", "setup"),), produces=("followup",), **_P),
    c("agent.literature", "agent", "analisis", "agent", "api", "T53", "Agente de literatura",
      "Traducirá reglas de los libros a lectura de mercado con cita de página. Aún no existe.",
      cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("data.snapshot", "snapshot"), ("library.cards", "library_card")),
      produces=("agent_report",), **_P),
    c("library.query", "library", "validacion", "service", "api", "T55", "Consulta a la biblioteca",
      "Responderá preguntas con fichas citadas usando un modelo de lenguaje que solo informa. "
      "Aún no existe.", consumes=(("library.cards", "library_card"),), produces=("answer",), **_P),
    c("bots.runner", "bots", "analisis", "service", "bots", "T57", "Ejecutor de bots",
      "Correrá bots públicos aislados, sin claves, y convertirá su salida en una señal común. "
      "Aún no existe.", cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("data.snapshot", "snapshot"),), produces=("bot_signal",), **_P),
    c("agent.bots", "agent", "analisis", "agent", "api", "T57", "Agente de bots",
      "Resumirá lo que opinan los bots como un analista más, puntuado por la puerta de "
      "validación. Aún no existe.", cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("bots.runner", "bot_signal"),), produces=("agent_report",), **_P),
    c("bots.scoring", "bots", "validacion", "engine", "bots", "T59", "Puntuación de bots",
      "Medirá a cada bot con la misma vara que a las estrategias propias y lo degradará si "
      "falla. Aún no existe.", consumes=(("bots.runner", "bot_signal"),),
      produces=("bot_score",), **_P),
    c("operation.experience_sync", "operation", "validacion", "service", "cli", "T61",
      "Experiencia compartida", "Unirá historiales de varios equipos exportando a una carpeta "
      "compartida. Aún no existe.", produces=("experience",), **_P),
    c("localai.engines", "localai", "analisis", "engine", "localai", "T63", "Motores de IA locales",
      "Capa que decidirá qué modelos locales caben en este equipo y dejará traza de cada uso. "
      "Aún no existe.", produces=("local_inference",), **_P),
    c("video.watcher", "video", "datos", "service", "video", "T64", "Vigilancia de canales",
      "Vigilará canales de YouTube elegidos y ordenará los videos por relevancia. "
      "Aún no existe.", cadence="cada hora", cadence_s=3600, produces=("video_queue",), **_P),
    c("video.transcribe", "video", "datos", "service", "video", "T65", "Transcripción",
      "Obtendrá el texto del video con marcas de tiempo, subtítulos primero y voz local si "
      "faltan. Aún no existe.", consumes=(("video.watcher", "video_queue"),),
      produces=("transcript",), **_P),
    c("video.scenes", "video", "datos", "service", "video", "T66", "Escenas y gráficos",
      "Extraerá fotogramas y leerá gráficos o texto en pantalla. Aún no existe.",
      consumes=(("video.watcher", "video_queue"),), produces=("frames",), **_P),
    c("video.claims", "video", "analisis", "engine", "video", "T67", "Afirmaciones",
      "Convertirá lo que dice el analista en afirmaciones concretas, cada una con su minuto. "
      "Aún no existe.", consumes=(("video.transcribe", "transcript"), ("video.scenes", "frames")),
      produces=("claims",), **_P),
    c("video.verify", "video", "analisis", "engine", "video", "T68", "Verificación contra datos",
      "Comprobará cada afirmación contra los datos reales y marcará contradicciones. "
      "Aún no existe.", consumes=(("video.claims", "claims"), ("data.store", "candles")),
      produces=("verified_claims",), **_P),
    c("video.reputation", "video", "validacion", "gate", "video", "T69", "Reputación de analistas",
      "Calibrará cuánto acertó cada analista antes de darle peso. Aún no existe.",
      consumes=(("video.verify", "verified_claims"),), produces=("reputation",), **_P),
    c("agent.video_intel", "agent", "analisis", "agent", "api", "T70", "Agente de videos",
      "Resumirá lo verificable de los videos como un analista más. Aún no existe.",
      cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("video.verify", "verified_claims"), ("video.reputation", "reputation")),
      produces=("agent_report",), **_P),
    c("observability.indexer", "observability", "validacion", "service", "observatory", "T73",
      "Indexador del observatorio", "Un solo proceso que carga los eventos de los archivos en una "
      "base para consultarlos. Aún no existe.", produces=("obs_index",), **_P),
    c("observability.map", "observability", "validacion", "view", "web", "T75",
      "Mapa del flujo de trabajo", "Vista que dibujará este mismo catálogo y marcará en vivo qué "
      "corre, qué falla y qué no tiene datos. Aún no existe.",
      consumes=(("observability.indexer", "obs_index"),), **_P),
)
