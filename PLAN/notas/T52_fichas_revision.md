# T52 — Fichas revisadas (◆)

**Estado:** revisada_usuario 138. Revisión del usuario el 2026-10-18: Nison y Murphy presentadas ficha a ficha y aprobadas; las 47 de conducta y cruces, presentadas y aprobadas por delegación expresa del usuario.

Generado desde `v2/eim/library/cards/` (138 fichas, todas `verificada_en_texto`: cada cita se comprobó contra el texto local con `python -m eim.library verify`). Las paráfrasis son mías; páginas = del archivo PDF. **Criterio de revisión:** que cada ficha diga lo que dice el autor (fidelidad), que las condiciones sean razonables para codificar y que el supuesto para BTC 24/7 sea aceptable.

Cambiar un estado: `python -m eim.library mark <estado> <id|libro> …` (desde `v2/`; `codificada` cuando T53 la implemente, `descartada` si se retira). Marcas: ✔ = comprobable (tiene condiciones operacionalizables), ✎ = cita textual breve, ⇄ = contradice a otra ficha.

## Steve Nison — *Japanese Candlestick Charting Techniques* (2001) · `nison_candles` · 43 fichas

- ✔ **La señal vale al cierre de la vela** · regla · p. 23, 24 · `nison_close_confirms`  
  Nison solo da por válida una señal con el cierre de la sesión: superar un nivel significa cerrar por encima, no tocarlo dentro de la vela. Por eso a veces hay que esperar al cierre (o a la apertura siguiente) antes de actuar.  
  *Cripto 24/7:* aplica al cierre de cada vela de 15 m, 1 h y 4 h (en 24/7 no hay cierre de sesión diario)
- · ✎ **Las velas no dan objetivos de precio** · advertencia · p. 24; p. 251 · `nison_no_price_targets`  
  Las velas dan señales tempranas de giro pero no dicen hasta dónde llegará el movimiento; ni un patrón ideal ni varios juntos predicen su extensión. Los objetivos se toman de herramientas occidentales (rangos, banderas, retrocesos).  
  *Cripto 24/7:* igual en BTC; el objetivo de una señal de velas debe salir de otra regla
- ✔ **Patrón de giro = cambio de tendencia, no inversión** · principio · p. 42, 43 · `nison_reversal_is_trend_change`  
  Un «patrón de giro» indica que la tendencia previa probablemente se detenga, no que se invierta: después puede venir un lateral, una reanudación o un giro. Conviene leerlo como patrón de cambio de tendencia y ajustar la operativa, no como orden de abrir en contra.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Abrir solo a favor de la tendencia mayor** · regla · p. 43 · `nison_trade_with_major_trend`  
  Una señal de giro solo justifica abrir posición si va en la dirección de la tendencia mayor. En un mercado alcista, un techo de velas sirve para cerrar largos, no para vender en corto; luego se busca una señal alcista en la corrección para volver a comprar.  
  *Cripto 24/7:* tendencia mayor = 4 h para señales de 1 h y 1 h para señales de 15 m (como el filtro de T48b)
- ✔ **Cuerpos que se achican: pierde impulso** · patrón · p. 37, 38, 39 · `nison_spinning_top`  
  El tamaño del cuerpo real mide el impulso: tras velas largas, un cuerpo pequeño (peonza) indica que el bando dominante pierde fuerza. Es una pista provisional de una sola sesión, más útil si coincide con un soporte o resistencia.  
  *Cripto 24/7:* «pequeño» relativo a los cuerpos recientes (p. ej. < 30 % del cuerpo medio de 20 velas)
- ✔ **Martillo** · patrón · p. 45, 46; p. 48, 49 · `nison_hammer`  
  Tras una caída (aunque sea corta), una vela con cuerpo real en la parte alta del rango, sombra inferior de al menos el doble del cuerpo y sin sombra superior (o muy corta) sugiere suelo. El martillo no necesita confirmación; cuanto más larga la sombra inferior y más pequeño el cuerpo, más significativo. Su mínimo queda como soporte.  
  *Cripto 24/7:* válido en velas de 15 m, 1 h y 4 h; el color del cuerpo no importa
- ✔ **Hombre colgado (requiere confirmación)** · patrón · p. 45, 49, 50; p. 52 · `nison_hanging_man`  
  La misma forma del martillo tras una subida extensa, idealmente en máximos, es un posible techo, pero exige confirmación bajista: como mínimo abrir por debajo de su cuerpo y, mejor, cerrar por debajo de él en la sesión siguiente. Sin ese cierre, la tendencia alcista sigue vigente.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h; «máximos» = máximo de N velas
- ✔ **Riesgo/beneficio antes de entrar con una vela** · gestión del riesgo · p. 47, 48, 49; p. 74; p. 109 · `nison_entry_on_pullback`  
  Antes de operar una señal de velas hay que mirar el riesgo/beneficio: al completarse el patrón el precio puede estar lejos del stop natural (el extremo del patrón). Alternativa del autor: esperar un retroceso hacia la zona del patrón (p. ej. la sombra inferior del martillo) y poner el stop más allá de su extremo; siempre debe existir un precio que diga que nos equivocamos.  
  *Cripto 24/7:* aplicable; la orden límite puede no llenarse (el bróker simulado mide el llenado)
- ✔ **Envolvente alcista / bajista** · patrón · p. 53, 54 · `nison_engulfing`  
  Con una tendencia definida (aunque sea corta), un cuerpo real que envuelve por completo el cuerpo anterior de color opuesto (las sombras no cuentan) es una señal importante de giro. Más fuerza si el primer cuerpo es una peonza y el segundo muy largo, si llega tras un movimiento largo o rápido y si el segundo día tiene mucho volumen.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h; en 24/7 la apertura ≈ cierre previo, así que basta con envolver el cuerpo (el autor lo acepta en divisas)
- ✔ **La envolvente marca soporte o resistencia** · regla · p. 55; p. 59, 60 · `nison_engulfing_levels`  
  El máximo de las dos velas de una envolvente bajista pasa a ser resistencia (al cierre) y el mínimo de una envolvente alcista, soporte. Sirve para entrar en el retroceso hacia esa zona cuando el patrón se completa lejos del extremo; un cierre por encima de la resistencia de una envolvente bajista es una ruptura alcista.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Nube oscura** · patrón · p. 60, 61, 62, 63 · `nison_dark_cloud_cover`  
  Tras una subida, una vela blanca fuerte seguida de otra que abre por encima del máximo previo y cierra muy dentro del cuerpo blanco es techo probable; cuanto más penetra, mejor. Si no cierra por debajo de la mitad del cuerpo blanco, conviene esperar más confirmación. El máximo de las dos velas queda como resistencia y como lugar del stop de un corto.  
  *Cripto 24/7:* en 24/7 casi nunca abre por encima del máximo previo; usar la variante «abre ≥ cierre previo» que el autor admite
- ✔ **Pauta penetrante** · patrón · p. 66, 67; p. 70 · `nison_piercing`  
  En una caída, una vela negra seguida de una blanca que abre más abajo (idealmente bajo el mínimo previo) y cierra por encima de la mitad del cuerpo negro sugiere suelo. Aquí el autor es menos flexible que con la nube oscura: si no pasa de la mitad (patrones on-neck, in-neck, thrusting), esperar un cierre más alto en la sesión siguiente.  
  *Cripto 24/7:* sin huecos en 24/7, exigir solo cierre > 50 % del cuerpo negro
- · ✎ **Stop protector desde la entrada** · gestión del riesgo · p. 61 · `nison_protective_stops`  
  El stop se fija al abrir la operación, cuando se es más objetivo, y se sale si el precio contradice o no confirma lo esperado. No hay lugar para la esperanza: peor que equivocarse es seguir equivocado; el stop es un costo del negocio y preservar el capital es la primera regla.  
  *Cripto 24/7:* aplica igual; el motor de riesgo ya exige stop en cada plan
- ✔ **Estrella de la mañana** · patrón · p. 72, 73; p. 77 · `nison_morning_star`  
  Suelo de tres velas: una negra larga, una de cuerpo pequeño que no toca el cuerpo anterior y una blanca que penetra profundamente en la primera vela negra. El hueco entre la 2.ª y la 3.ª no es necesario; lo decisivo es la peonza y la penetración de la 3.ª. El mínimo de las tres velas actúa como soporte.  
  *Cripto 24/7:* en 24/7 los cuerpos suelen tocarse; el autor acepta esa flexibilidad en intradía
- ✔ **Estrella vespertina** · patrón · p. 76, 77 · `nison_evening_star`  
  Techo de tres velas tras una subida: blanca larga, estrella (cuerpo pequeño) y negra que cierra muy dentro del cuerpo blanco. El segundo hueco rara vez aparece y no es necesario; importa cuánto penetra la 3.ª. Más fiable si los cuerpos no se solapan y con volumen bajo en la 1.ª y alto en la 3.ª. Los máximos del patrón quedan como resistencia.  
  *Cripto 24/7:* igual que la estrella de la mañana (sin exigir huecos)
- ✔ **Estrellas doji y «bebé abandonado»** · patrón · p. 80, 81 · `nison_doji_star_abandoned_baby`  
  Si la vela central de una estrella vespertina o de la mañana es un doji, el patrón gana relevancia. Si además las sombras del doji no tocan las de la 1.ª y la 3.ª vela (huecos a ambos lados) es un «bebé abandonado», equivalente a una isla occidental; el autor lo considera muy raro.  
  *Cripto 24/7:* los huecos entre sombras casi no existen en BTC 24/7 en 15 m/1 h; el bebé abandonado será rarísimo
- · **Mercados sin apertura/cierre separados: más flexibilidad** · advertencia · p. 74, 75; p. 231 · `nison_continuous_markets`  
  En mercados donde la apertura casi coincide con el cierre previo (divisas, algunos índices, gráficos intradía de 15 min), Nison acepta que los cuerpos de una estrella se toquen y que una envolvente abra igual al cierre previo. Supuesto clave para BTC 24/7: los criterios basados en huecos deben relajarse.  
  *Cripto 24/7:* supuesto central: BTC perpetuo cotiza 24/7 sin sesión; aplicar la versión flexible de todos los patrones con huecos
- ✔ **Estrella fugaz** · patrón · p. 84, 85, 86 · `nison_shooting_star`  
  Tras una subida, una vela de cuerpo pequeño en la parte baja del rango con sombra superior larga muestra que el alza no se sostuvo. Al ser de una sola sesión no es un giro mayor ni una resistencia clave; varias estrellas fugaces en el mismo nivel refuerzan esa resistencia, y un cierre por encima de sus máximos anula la lectura bajista.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h; el hueco previo no es necesario
- ✔ **Martillo invertido (requiere confirmación)** · patrón · p. 88, 89 · `nison_inverted_hammer`  
  La forma de la estrella fugaz tras una caída es un martillo invertido, posible suelo, pero necesita confirmación alcista: que la sesión siguiente abra y, sobre todo, cierre por encima de su cuerpo real (los cortos de ese día quedan perdiendo).  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Harami y harami cruz** · patrón · p. 91, 92 · `nison_harami`  
  Un cuerpo pequeño contenido en un cuerpo anterior inusualmente largo indica que el mercado «pierde el aliento»: posible giro, más a menudo pausa. Cuanto más pequeño el 2.º cuerpo, más potente; si es un doji (harami cruz) es aún más fuerte y, según el autor, más eficaz en techos. A diferencia de la vela interior occidental, solo el cuerpo debe quedar dentro.  
  *Cripto 24/7:* «inusualmente largo» = cuerpo > 1,5 × cuerpo medio de 20 velas
- ✔ **Pinzas (máximos o mínimos iguales)** · patrón · p. 96, 97 · `nison_tweezers`  
  Dos o más velas con máximos (techo) o mínimos (suelo) coincidentes. En diario o intradía tener el mismo máximo no basta: solo cuentan si además forman otra señal de velas o si la 1.ª es larga y la 2.ª pequeña. En semanal o mensual pueden ser giros importantes por sí solas.  
  *Cripto 24/7:* en 15 m/1 h/4 h solo como refuerzo de otra señal
- ✔ **Belt-hold (vela de apertura afeitada)** · patrón · p. 102 · `nison_belt_hold`  
  Belt-hold alcista: vela blanca larga que abre en el mínimo (o casi) y cierra cerca del máximo; en zona de precios bajos anticipa subida. La bajista es la negra que abre en el máximo y cae toda la sesión. Cuanto más larga, más significativa; un cierre más allá de la vela anula la señal.  
  *Cripto 24/7:* en 24/7 la apertura ≈ cierre previo, así que la vela «afeitada» depende solo del recorrido intravela
- ✔ **Tres cuervos negros** · patrón · p. 106, 107 · `nison_three_black_crows`  
  Tres velas negras descendentes que cierran en o cerca de sus mínimos, idealmente abriendo dentro del cuerpo anterior, anticipan bajadas si aparecen en precios altos o tras un alza madura. Como se completa con la 3.ª vela, la señal llega tarde y sirve más a operadores de plazo largo.  
  *Cripto 24/7:* válido en 1 h/4 h; en 15 m puede ser ruido
- ✔ **Tres soldados blancos; bloque de avance** · patrón · p. 108, 109 · `nison_three_white_soldiers`  
  Tres velas blancas largas con cierres cada vez más altos, cada una cerrando cerca de su máximo y abriendo dentro o cerca del cuerpo anterior, muestran fuerza si salen de una zona baja o lateral. Si la 2.ª y 3.ª se debilitan (cuerpos menores, sombras superiores largas) es un bloque de avance: proteger largos, no vender en corto.  
  *Cripto 24/7:* válido en 1 h/4 h
- ✔ **Tres montañas / tres ríos** · patrón · p. 112 · `nison_three_mountains`  
  Equivalente japonés del triple techo: tres intentos fallidos de superar un máximo marcan un techo mayor, idealmente confirmado por una señal bajista de velas en la última cima. Si la cima central es la más alta es el «tres Budas», igual al hombro-cabeza-hombro; los tres ríos son el suelo equivalente.  
  *Cripto 24/7:* en 4 h; tolerancia de igualdad de máximos a definir
- ✔ ✎ **Ventanas (huecos): continuación y soporte** · regla · p. 135, 136, 137 · `nison_windows`  
  Una ventana es un hueco entre las sombras (no basta con que no se toquen los cuerpos). Es señal de continuación: con ventana alcista, comprar en retrocesos; con bajista, vender en rebotes. Toda la ventana actúa como soporte o resistencia y un cierre más allá de su extremo anula la tendencia; el tamaño no importa.  
  *Cripto 24/7:* los huecos reales son raros en BTC perpetuo 24/7 (salvo picos de volatilidad); muestra pequeña
- ✔ **Tres métodos alcistas / bajistas** · patrón · p. 151, 152 · `nison_rising_three_methods`  
  Continuación: una vela larga, de 2 a 5 velas pequeñas que retroceden o van de lado sin salirse del rango máximo-mínimo de la primera, y una vela final fuerte que cierra más allá del cierre de la primera. Es un «respiro» parecido a la bandera occidental; completarlo tarde puede empeorar el riesgo/beneficio.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Doji: mercado «cansado», mejor en techos** · patrón · p. 163, 164, 165, 166 · `nison_doji_tops`  
  Un doji tras una vela blanca alta o en sobrecompra indica que el mercado está «cansado»: la tendencia pasa de alcista a alcista/neutral, no a bajista. Cuenta más si hay pocos doji en el gráfico y si confirma otra señal. Según el autor funciona mejor en techos; en caídas necesita más confirmación.  
  *Cripto 24/7:* «doji» = cuerpo < 10 % del rango de la vela; el propio autor pide comprobar qué funciona en cada mercado
- ✔ **Doji con nuevo máximo de cierre: esperar confirmación** · regla · p. 178 · `nison_doji_new_high_close`  
  Si el doji es a la vez el cierre más alto del movimiento, la tendencia sigue alcista hasta que haya confirmación bajista: un cierre en la sesión siguiente por debajo del cierre del doji.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Doji lápida y doji libélula** · patrón · p. 170, 171 · `nison_gravestone_dragonfly`  
  Doji lápida: apertura, mínimo y cierre en el mínimo con sombra superior larga; es la estrella fugaz extrema y su fuerte son los techos. Doji libélula: apertura y cierre en el máximo con sombra inferior larga, su contraparte alcista. Ninguno anticipa la magnitud del movimiento siguiente.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Sombras largas repetidas en un nivel** · patrón · p. 56; p. 86 · `nison_shadows_rejection`  
  Una serie de sombras superiores largas cerca del mismo precio indica que el mercado rechaza precios más altos (resistencia); una serie de sombras inferiores largas, demanda (soporte). Varias señales en el mismo nivel refuerzan la zona.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Convergencia de señales en un mismo precio** · principio · p. 188 · `nison_convergence`  
  Las velas son una herramienta, no un sistema: deben combinarse con otros indicadores. Cuantas más señales (de velas y occidentales) coinciden en un mismo soporte o resistencia, más probable es el giro.  
  *Cripto 24/7:* aplicable; es la idea del puntaje de confluencia de las sugerencias
- ✔ **Spring y upthrust (rupturas falsas)** · regla · p. 203, 204; p. 75 · `nison_springs_upthrusts`  
  Spring: el precio rompe un soporte horizontal y vuelve a cerrar por encima → comprar, stop bajo el mínimo reciente (al cierre), objetivo el techo del rango. Upthrust: lo contrario en la resistencia. Más fiable si la ruptura ocurre con poco volumen y la vuelta con mucho. En general, nuevos extremos que no se sostienen anticipan giro.  
  *Cripto 24/7:* frecuente en BTC (barridas de liquidez); medir en 15 m/1 h
- ✔ **Cambio de polaridad** · regla · p. 210, 211 · `nison_change_of_polarity`  
  El soporte roto se convierte en resistencia y la resistencia rota en soporte. El autor lo explica por el apego emocional al precio de entrada: quienes compraron en un soporte que luego se perforó venden al volver a ese precio para salir sin pérdida.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Retrocesos 38/50/62 % solo con vela que confirme** · regla · p. 216, 217 · `nison_retracement_needs_candle`  
  Los retrocesos de 38 %, 50 % y 62 % de un tramo son soportes o resistencias potenciales, pero el autor no compraría ni vendería en ellos salvo que una señal de velas lo confirme en ese nivel.  
  *Cripto 24/7:* válido en 1 h/4 h
- ✔ **Medias móviles con velas** · regla · p. 222, 223 · `nison_moving_averages`  
  Usos que propone: precio sobre/bajo la media como tendencia; cierre por encima o por debajo de la media como señal; pendiente de la media; cruce de una media corta sobre una larga («cruz dorada») o bajo ella («cruz de la muerte»). Usa 5 y 30 días en acciones y 40 y 65 en futuros, sin optimizar.  
  *Cripto 24/7:* los periodos diarios no se trasladan 1:1 a 1 h; tratar el periodo como parámetro a validar
- ✔ **RSI: sobrecompra, sobreventa y divergencias** · regla · p. 230, 231 · `nison_rsi_divergence`  
  RSI de 14: por encima de 70 sobrecompra y por debajo de 30 sobreventa. Divergencia negativa: el precio hace un nuevo máximo y el RSI no; positiva, al revés en mínimos. La divergencia pesa más en zonas extremas, y una señal de velas que coincide con ella se refuerza.  
  *Cripto 24/7:* válido en 1 h/4 h
- ✔ **Sobrecompra sin vela de giro: no vender** · regla · p. 236 · `nison_oscillator_needs_candle`  
  Una lectura de sobrecompra del oscilador sin una señal de giro de velas no basta para vender: el autor solo actúa cuando el oscilador extremo coincide con un patrón de giro (doji, envolvente, hombre colgado confirmado).  
  *Cripto 24/7:* válido en 1 h/4 h
- ✔ **Estocástico** · regla · p. 237, 238 · `nison_stochastics`  
  Estocástico (%K lento suavizado 3 y %D = media de 3 del %K): 80 o más es sobrecompra y 20 o menos sobreventa. Una señal de compra completa exige %D ≤ 20, divergencia positiva y cruce del %K por encima del %D (simétrico para venta).  
  *Cripto 24/7:* válido en 1 h
- ✔ **El volumen confirma la tendencia y las velas** · regla · p. 243, 244, 245 · `nison_volume_confirms`  
  El volumen debe crecer en la dirección de la tendencia; si baja mientras la tendencia avanza, hay menos razones para esperar que siga. Se mira el volumen relativo (picos frente a las sesiones previas), no la cifra absoluta; un martillo con volumen anormalmente alto reduce la probabilidad de volver a su mínimo.  
  *Cripto 24/7:* volumen del perpetuo de Binance como proxy; los picos por liquidaciones pueden distorsionarlo
- ✔ **Objetivo por ruptura de rango (caja)** · regla · p. 252 · `nison_box_breakout_target`  
  Al salir de un rango lateral, el precio tiende a seguir en la dirección de la ruptura al menos la altura del rango, medida desde el nivel roto. El objetivo sirve para cerrar la posición, no para abrir la contraria, salvo que allí aparezca además una señal de giro.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- ✔ **Objetivo de banderas y banderines (conservador)** · regla · p. 258, 259 · `nison_flag_target`  
  Tras un tramo vertical (mástil) y una pausa breve en forma de bandera o banderín, el objetivo es la altura del mástil. El método tradicional la suma al techo de la bandera; Nison, más conservador, la suma desde el borde inferior para no perder la salida.  
  *Cripto 24/7:* válido en 15 m/1 h/4 h
- · **Los patrones son guías subjetivas** · advertencia · p. 22, 23; p. 69; p. 166 · `nison_subjectivity`  
  Las definiciones de los patrones son guías, no reglas rígidas; un patrón imperfecto se juzga por cómo y dónde se formó, y esa subjetividad dificulta reconocerlos por computadora. El autor pide comprobar con la experiencia qué patrones funcionan en cada mercado: codificarlos exige umbrales explícitos y validación.  
  *Cripto 24/7:* obliga a fijar umbrales antes de probar (puerta T49)

## John J. Murphy — *Technical Analysis of the Financial Markets* (1999) · `murphy_ta` · 48 fichas

- · **Premisas del análisis técnico** · principio · p. 39, 40 · `murphy_three_premises`  
  Murphy apoya el análisis técnico en tres premisas: la acción del mercado lo descuenta todo (el precio refleja oferta y demanda), los precios se mueven en tendencias y la historia se repite. Las herramientas sirven para identificar tendencias pronto y operar a su favor.  
  *Cripto 24/7:* premisas generales; su validez en BTC es justo lo que mide la puerta T49
- ✔ **Tendencia = secuencia de máximos y mínimos** · regla · p. 86, 87; p. 93, 94 · `murphy_trend_definition`  
  Una tendencia alcista es una serie de máximos y mínimos sucesivamente más altos; la bajista, más bajos; máximos y mínimos horizontales son un lateral. Para que la subida siga, cada mínimo debe superar al anterior; no superar el máximo previo es el primer aviso y perforar el mínimo previo hace probable el giro.  
  *Cripto 24/7:* pivotes detectados con un umbral fijo (p. ej. fractales de N velas o ZigZag en ATR)
- ✔ **Un tercio del tiempo en lateral: quedarse fuera** · regla · p. 88, 89 · `murphy_sideways_stand_aside`  
  El mercado se mueve en tres direcciones y, según el autor, al menos un tercio del tiempo va de lado. Los sistemas seguidores de tendencia funcionan mal o nada en esos tramos y ahí sufren sus mayores pérdidas; cuando el mercado va de lado, lo más sensato suele ser no operar.  
  *Cripto 24/7:* el agente `regime` ya clasifica lateral/tendencia; la regla se prueba como filtro
- ✔ **Tres grados de tendencia; el corto plazo para entrar** · principio · p. 89, 90, 91 · `murphy_three_degrees_of_trend`  
  Cada tendencia es parte de otra mayor y se compone de otras menores (mayor, intermedia y de corto plazo). Los métodos de seguimiento se centran en la intermedia y usan la de corto plazo para el momento de entrada: en una tendencia intermedia alcista, los retrocesos cortos sirven para abrir largos.  
  *Cripto 24/7:* equivalencia 4 h (intermedia) / 1 h y 15 m (corto plazo)
- ✔ **La tendencia sigue vigente hasta que da señales de giro** · principio · p. 65, 66 · `murphy_dow_trend_persists`  
  Principio de Dow: una tendencia se presume vigente hasta que da señales definidas de haberse invertido; las probabilidades suelen favorecer que continúe. Lo más difícil es distinguir una corrección secundaria del primer tramo de una tendencia nueva.  
  *Cripto 24/7:* aplicable en 4 h
- ✔ **Soporte y resistencia; qué los hace fuertes** · regla · p. 92, 93; p. 97 · `murphy_support_resistance`  
  El soporte suele ser un mínimo de reacción previo y la resistencia un máximo previo. Un nivel pesa más cuanto más tiempo se negoció allí, cuanto más volumen hubo y cuanto más reciente es la negociación, porque más participantes tienen interés en ese precio.  
  *Cripto 24/7:* el perfil de volumen del almacén puede medir la «cantidad negociada» en la zona
- ✔ **Inversión de papeles tras una penetración significativa** · regla · p. 96, 98; p. 100, 101 · `murphy_role_reversal`  
  Un soporte perforado por un margen significativo se vuelve resistencia, y viceversa. Como referencia, algunos usan un 3 % de penetración para niveles mayores y en torno al 1 % para los de corto plazo; el cambio de papel solo ocurre si el precio se aleja lo bastante como para convencer a los participantes de su error.  
  *Cripto 24/7:* umbral en múltiplos de ATR en lugar de % fijo, porque la volatilidad de BTC varía
- ✔ **Números redondos como soporte/resistencia** · regla · p. 101, 102 · `murphy_round_numbers`  
  Los números redondos tienden a frenar subidas y bajadas porque los operadores fijan allí sus objetivos. Recomendación táctica: comprar con límite justo por encima del número redondo, vender justo por debajo, y no poner stops en el número exacto (en largos, por debajo; en cortos, por encima).  
  *Cripto 24/7:* en BTC, múltiplos de 1 000 y 5 000/10 000 USDT
- ✔ **Línea de tendencia: 2 puntos la trazan, el 3.º la valida** · regla · p. 102, 103, 104; p. 106 · `murphy_trendline_validity`  
  Hacen falta dos mínimos ascendentes para trazar una directriz alcista tentativa y un tercer toque con rebote para validarla. Su importancia crece con el tiempo que lleva intacta y con el número de toques; se traza sobre el rango completo de cada vela, no solo sobre los cierres.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Ruptura válida de una línea (filtros de precio y tiempo)** · regla · p. 105; p. 108, 109 · `murphy_trendline_break`  
  Mientras la directriz no se rompa, los retrocesos hacia ella son zona de compra; su ruptura es uno de los mejores avisos tempranos de cambio y pide cerrar las posiciones de la tendencia previa. Un cierre más allá pesa más que una penetración intradía; filtros habituales: 3 % (líneas mayores), ~1 % (corto plazo) o dos cierres seguidos.  
  *Cripto 24/7:* la «regla de 2 días» pasa a 2 velas del marco; filtro de precio en ATR
- ✔ **Proyección tras romper una línea; principio del abanico** · regla · p. 111, 112, 113 · `murphy_trendline_measuring`  
  Tras romper una directriz, el precio suele recorrer más allá de ella una distancia similar a la que llegó a separarse del otro lado. Principio del abanico: cuando se rompen sucesivas líneas cada vez más planas, la ruptura de la tercera es la señal válida de giro; las líneas rotas actúan luego con el papel opuesto.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Canales: entrada en la directriz, salida en la paralela** · regla · p. 117, 119, 120; p. 122 · `murphy_channels`  
  Con un canal establecido, la directriz sirve para abrir y la línea paralela para tomar beneficio. No alcanzar un lado del canal suele anticipar la ruptura del otro; romper la paralela a favor de la tendencia indica aceleración. Tras salir del canal, el precio suele recorrer una distancia igual a su anchura.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Retrocesos de 33–66 % (y 38/62 %)** · regla · p. 63; p. 122, 123, 124; p. 449 · `murphy_retracements`  
  Las correcciones suelen retroceder entre un tercio y dos tercios del tramo previo, a menudo cerca del 50 %; el autor combina 33–38 % (mínimo) y 62–66 % (máximo). Si la corrección pasa del 66 % es más probable un giro que un retroceso y suele recorrer el 100 % del tramo. La zona de 40–60 % sirve para entrar a favor.  
  *Cripto 24/7:* aplicable en 15 m/1 h/4 h
- ✔ **Día de giro y clímax de ventas** · patrón · p. 127, 128, 129, 130 · `murphy_reversal_days`  
  Día de giro bajista: nuevo máximo del movimiento y cierre por debajo del cierre anterior (alcista, al revés). Cuanto más amplio el rango y mayor el volumen, más significativo; si además envuelve el rango previo (día exterior), más aún. El clímax de ventas con volumen enorme suele marcar un mínimo importante. Los giros semanales y mensuales pesan más.  
  *Cripto 24/7:* aplicable a velas de 4 h y diarias; en 15 m es ruido
- ✔ **Huecos: de ruptura, de continuación y de agotamiento** · regla · p. 131, 132, 133, 134; p. 449 · `murphy_gaps`  
  El hueco de ruptura aparece al completar un patrón, con volumen alto, y a menudo no se llena; el de continuación surge hacia la mitad del movimiento (permite estimar el resto duplicando lo recorrido); el de agotamiento llega al final y cerrar por debajo lo confirma. Un cierre bajo un hueco alcista es debilidad; comprar el retroceso al hueco con stop bajo él.  
  *Cripto 24/7:* los huecos casi no existen en BTC perpetuo 24/7; muestra mínima en 15 m/1 h
- ✔ **Condiciones comunes de los patrones de giro** · principio · p. 138, 139, 140 · `murphy_reversal_preconditions`  
  Todo patrón de giro exige una tendencia previa que revertir; el primer aviso suele ser romper una directriz importante; cuanto mayor el patrón (altura y duración), mayor el movimiento siguiente; los techos son más cortos y volátiles que los suelos, y el volumen importa más en las rupturas alcistas.  
  *Cripto 24/7:* aplicable en 4 h
- ✔ **Hombro-cabeza-hombro** · patrón · p. 140, 141, 143, 144; p. 145, 146 · `murphy_head_and_shoulders`  
  Tres máximos con el central más alto, volumen menor en la cabeza y aún menor en el hombro derecho. Solo se completa con un cierre decisivo bajo la línea de cuello (filtro 1–3 % o dos cierres). Objetivo mínimo: distancia cabeza–cuello proyectada desde la ruptura; máximo: retroceso total del movimiento previo. Suele haber un retesteo del cuello.  
  *Cripto 24/7:* aplicable en 4 h; detección automática exige reglas de pivotes fijadas antes de probar
- ✔ **En los suelos el volumen de la ruptura es imprescindible** · regla · p. 140, 148, 149 · `murphy_inverse_hs_volume`  
  En el hombro-cabeza-hombro invertido (y en los suelos en general) la ruptura del cuello debe venir con una explosión de volumen: los mercados pueden caer por inercia, pero no suben sin compras agresivas. Si la ruptura alcista no trae más volumen, todo el patrón queda en duda; el retesteo es más frecuente en suelos.  
  *Cripto 24/7:* volumen del perpetuo como medida; cuidado con picos por liquidaciones
- ✔ **Patrón fallido: salir rápido** · gestión del riesgo · p. 150, 151, 152 · `murphy_failed_patterns`  
  Si tras romper el cuello el precio vuelve a cerrar decisivamente al otro lado, el patrón ha fallado: ningún patrón es infalible. La clave para sobrevivir es mantener pequeñas las pérdidas y salir enseguida cuando el gráfico avisa de que se está del lado equivocado.  
  *Cripto 24/7:* igual
- ✔ **Doble techo / doble suelo (término abusado)** · patrón · p. 154, 155, 157; p. 159, 162 · `murphy_double_top`  
  Dos máximos a nivel similar con menos volumen en el segundo; solo existe al cerrar bajo el mínimo intermedio, mejor con volumen; objetivo = altura proyectada. Lo normal es que el precio retroceda desde un máximo previo sin formar techo: el término se abusa. Mejor con al menos un mes entre picos; filtros para las rupturas falsas (trampa alcista).  
  *Cripto 24/7:* «un mes» en diario ≈ 30 velas del marco usado; validar
- · **Giros en V: casi sin aviso** · advertencia · p. 162, 164 · `murphy_v_reversals`  
  Los giros en V (picos) ocurren muy rápido, sin fase de transición, normalmente en mercados sobreextendidos ante una noticia adversa; a veces el único aviso es un día de giro con volumen muy alto. Los patrones de giro clásicos no los capturan.  
  *Cripto 24/7:* frecuentes en BTC por cascadas de liquidación; argumento para bandas anchas en los escenarios
- ✔ **Triángulos simétrico, ascendente y descendente** · patrón · p. 169, 170, 171, 172; p. 173, 176, 177 · `murphy_triangles`  
  El simétrico es de continuación (dirección de la tendencia previa), necesita al menos cuatro puntos de giro y la ruptura debería ocurrir entre 2/3 y 3/4 del ancho hasta el vértice; más tarde pierde fuerza. El ascendente es alcista y el descendente bajista estén donde estén. Volumen que se contrae y crece en la ruptura; objetivo = altura de la base.  
  *Cripto 24/7:* aplicable en 1 h/4 h con duraciones escaladas
- ✔ **Banderas y banderines (a media asta)** · patrón · p. 178, 179, 180, 181, 182 · `murphy_flags_pennants`  
  Tras un movimiento casi vertical con volumen alto, una pausa breve (1–3 semanas) con volumen muy bajo: bandera inclinada contra la tendencia o banderín convergente. La tendencia se reanuda con un estallido de volumen. Suelen aparecer hacia la mitad del movimiento: el tramo posterior repite el mástil medido desde la ruptura. Según el autor, de los más fiables.  
  *Cripto 24/7:* en 15 m/1 h la pausa dura pocas decenas de velas
- ✔ **Cuñas: la inclinación contraria manda** · patrón · p. 183, 184, 185 · `murphy_wedges`  
  La cuña tiene dos líneas convergentes con una inclinación marcada contra la tendencia. Regla general del autor, esté donde esté: la cuña ascendente es bajista y la descendente alcista; suele ser de continuación y, con menos frecuencia, de giro.  
  *Cripto 24/7:* aplicable en 4 h
- ✔ **Rectángulo (rango): operar los extremos o esperar la ruptura** · patrón · p. 184, 187, 188 · `murphy_rectangle`  
  Un rango entre dos horizontales suele resolverse en la dirección de la tendencia previa; el volumen de los tramos indica hacia dónde (más en las subidas = continuación alcista). Se pueden operar los extremos con riesgo acotado y, al romper, salir de la última operación y girarse; objetivo = altura del rango.  
  *Cripto 24/7:* aplicable en 15 m/1 h/4 h
- ✔ **Movimiento medido (dos tramos iguales)** · regla · p. 188, 189, 190 · `murphy_measured_move`  
  En un movimiento ordenado, tras un primer tramo y una corrección que retrocede entre un tercio y la mitad, el segundo tramo tiende a igualar al primero: objetivo = altura del primer tramo sumada al mínimo de la corrección.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Reglas de volumen** · regla · p. 64; p. 199, 200, 201, 202 · `murphy_volume_rules`  
  El volumen debe crecer en la dirección de la tendencia (más en subidas y menos en retrocesos si es alcista). Un nuevo máximo con volumen decreciente es divergencia y aviso; la resolución de un patrón debe llegar con más volumen. El volumen precede al precio; el OBV (volumen acumulado con signo del cierre) ayuda a medir su dirección.  
  *Cripto 24/7:* volumen y compra agresora (taker_buy_v, T34) del perpetuo
- ✔ **Reglas de interés abierto (futuros)** · regla · p. 198; p. 207, 208, 209, 210, 211, 212 · `murphy_open_interest_rules`  
  Interés abierto creciente en tendencia alcista: alcista (dinero nuevo); decreciente en subida: bajista (cierre de cortos); creciente en caída: bajista; decreciente en caída: alcista (largos liquidando). Que se aplane al final de una tendencia avisa de cambio; un interés muy alto en techos agrava la caída; si crece en un rango, la ruptura se intensifica.  
  *Cripto 24/7:* el interés abierto del perpetuo (snapshot.open_interest) sustituye al de futuros; el funding no tiene equivalente en el libro
- · ✎ **La media móvil sigue, no anticipa** · advertencia · p. 234; p. 253 · `murphy_ma_is_a_follower`  
  La media móvil es un seguidor de tendencia con retraso: confirma el cambio después de que ocurre. Funciona muy bien en tendencia y muy mal cuando el mercado va de lado, que puede ser entre un tercio y la mitad del tiempo; por eso es peligroso depender solo de ella.  
  *Cripto 24/7:* igual en BTC
- ✔ **Cruces de medias (1, 2 y 3 medias)** · regla · p. 238, 239, 240; p. 241, 242, 243; p. 262 · `murphy_moving_average_crossovers`  
  Una media: comprar cuando el cierre la supera (mejor si la media gira en esa dirección). Dos medias: compra cuando la corta cruza sobre la larga (5/20, 10/50; en futuros 4/9, 9/18, 10/40). Tres medias 4-9-18: alerta con la de 4 y confirmación al cruzar la 9 sobre la 18. Medias cortas: señales antes y más falsas.  
  *Cripto 24/7:* periodos en velas del marco, no en días; validar fuera de muestra
- ✔ **Envolventes y bandas de Bollinger** · regla · p. 244; p. 248, 249, 250 · `murphy_bollinger_envelopes`  
  Envolventes del 3 % sobre una media de 21 días marcan sobreextensión de corto plazo. Bandas de Bollinger (media de 20 ± 2 desviaciones): tocar la banda indica sobrecompra o sobreventa; tras rebotar en la inferior y cruzar la media, objetivo la superior. En tendencia fuerte el precio va entre banda y media; bandas muy estrechas anticipan tendencia nueva.  
  *Cripto 24/7:* el 3 % fijo no escala a la volatilidad de BTC; usar bandas en desviaciones
- ✔ **Regla de las 4 semanas (ruptura de canal de Donchian)** · regla · p. 256, 257, 258 · `murphy_weekly_rule`  
  Comprar cuando el precio supera los máximos de las cuatro semanas previas completas y vender cuando perfora sus mínimos; versión no continua: salir con una ruptura contraria de 1–2 semanas. El autor cita estudios en que las rupturas de canal y los cruces de medias quedaron entre los pocos sistemas rentables (Lukac, 1975–84: 4 de 12; 2 eran de canal).  
  *Cripto 24/7:* canal de 20 velas en 4 h o 1 h; los estudios citados no incluyen cripto
- · **Optimizar solo con prueba fuera de muestra** · advertencia · p. 261, 262 · `murphy_optimize_out_of_sample`  
  La optimización de parámetros no es el Santo Grial: el procedimiento correcto es elegir los parámetros con una parte de los datos y probarlos en otra («fuera de muestra»), para acercarse a lo que daría operar de verdad. Quien sigue muchos mercados debería usar los mismos parámetros en todos.  
  *Cripto 24/7:* coincide con la puerta T49 (fuera de muestra, versiones y registro de intentos)
- ✔ **El oscilador se subordina a la tendencia** · regla · p. 267; p. 272; p. 292 · `murphy_oscillator_with_trend`  
  El oscilador es secundario y debe subordinarse al análisis de tendencia: comprar sobreventa en tendencia alcista y vender sobrecompra en bajista; usar los cruces de la línea cero solo a favor de la tendencia. Usar una divergencia como excusa para operar contra la tendencia general suele salir caro.  
  *Cripto 24/7:* aplicable en 15 m/1 h con tendencia de 4 h
- ✔ **Tres usos del oscilador** · regla · p. 268; p. 269, 271 · `murphy_oscillator_three_uses`  
  Los osciladores son más útiles en tres casos: en lecturas extremas (sobrecompra o sobreventa), con divergencias respecto del precio mientras están en zona extrema, y en el cruce de la línea media o cero a favor de la tendencia. El momento (cierre menos cierre de hace N) se adelanta al precio.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Ignorar el oscilador al inicio de una tendencia** · regla · p. 285, 286; p. 292, 293 · `murphy_oscillators_early_trend`  
  Tras una ruptura importante, los osciladores llegan enseguida a extremos y se quedan ahí: en esa fase conviene ignorarlos y tomar la posición, y darles más peso cuando la tendencia madura. La primera entrada en zona extrema es solo un aviso; la que cuenta es la segunda, si no confirma el nuevo extremo del precio.  
  *Cripto 24/7:* aplicable
- ✔ **RSI: 70/30, oscilaciones fallidas y 50** · regla · p. 281, 282, 283; p. 285, 286 · `murphy_rsi`  
  RSI de 14 (también 9): sobre 70 sobrecompra y bajo 30 sobreventa; en mercados alcistas el techo pasa a 80 y en bajistas el suelo a 20. Lo más valioso son las oscilaciones fallidas y divergencias por encima de 70 o por debajo de 30; volver a cruzar 30 al alza (o 70 a la baja) sirve de señal, y el 50 actúa como soporte o resistencia.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **Estocástico lento** · regla · p. 287, 288 · `murphy_stochastics`  
  %K = posición del cierre en el rango de 14 periodos; %D = media de 3 del %K; la versión lenta suaviza otra vez. La señal principal es la divergencia del %D en zona extrema (sobre 80 o bajo 20) y el disparo llega cuando el %K cruza al %D. Se pueden usar las semanales para la dirección y las diarias para la entrada.  
  *Cripto 24/7:* aplicable en 15 m/1 h
- ✔ **MACD e histograma** · regla · p. 293, 294, 295, 296 · `murphy_macd`  
  MACD (12, 26, 9): señal al cruzar la línea MACD con la de señal; las mejores compras ocurren muy por debajo de cero y las mejores ventas muy por encima; hay divergencias como en otros osciladores. El histograma gira antes que el cruce y sirve sobre todo para salir de posiciones, no para abrir contra la tendencia.  
  *Cripto 24/7:* aplicable en 1 h/4 h
- ✔ **El marco mayor filtra las señales del menor** · regla · p. 297; p. 452 · `murphy_trade_with_longer_trend`  
  Las señales semanales pesan más que las diarias: el marco mayor fija la dirección y el menor afina la entrada y la salida; una señal diaria solo se sigue si coincide con la semanal. El proceso debe ir de lo largo a lo corto: mensual y semanal, luego diario y por último intradía.  
  *Cripto 24/7:* 4 h filtra 1 h y 1 h filtra 15 m (ya lo aplica T48b)
- · **Límites de capital por operación y por mercado** · gestión del riesgo · p. 442, 443 · `murphy_position_limits`  
  Pautas del autor para futuros: invertir como máximo el 50 % del capital (el resto, en reserva), comprometer como margen en un mercado solo el 10–15 % del capital, arriesgar como mucho un 5 % del capital en una operación y limitar el margen por grupo de mercados correlacionados al 20–25 %.  
  *Cripto 24/7:* el 5 % es muy alto para perpetuos apalancados 24/7; el motor de riesgo vigente es más estricto y manda
- ✔ **Dónde poner el stop** · gestión del riesgo · p. 444; p. 448, 450 · `murphy_stop_placement`  
  Usar siempre stops protectores, más holgados cuanto más volátil es el mercado (demasiado cerca, el ruido los salta; demasiado lejos, pérdidas grandes). El stop debe quedar más allá de un soporte o resistencia válidos y el tamaño de la posición se ajusta para que esa distancia no supere el riesgo máximo.  
  *Cripto 24/7:* holgura en múltiplos de ATR del marco
- ✔ **Relación beneficio/riesgo de al menos 3 a 1** · gestión del riesgo · p. 444, 445 · `murphy_reward_risk`  
  Según el autor, los mejores operadores de futuros solo ganan en torno al 40 % de sus operaciones; para salir adelante las ganancias deben superar a las pérdidas. Pauta habitual: considerar una operación solo si el beneficio potencial es al menos tres veces la pérdida posible, y dejar correr las ganancias cortando pronto las pérdidas.  
  *Cripto 24/7:* con costos de perpetuos, la relación debe medirse neta de comisiones y funding
- ✔ **Unidades de tendencia y unidades de operación** · gestión del riesgo · p. 445, 446 · `murphy_trending_trading_units`  
  Operar con varias unidades: una parte de «tendencia» con stops holgados para aprovechar los movimientos grandes y otra de «operación» que toma beneficio en el primer objetivo o usa un stop ajustado; si la tendencia sigue, se reponen. Evitar operar una sola unidad.  
  *Cripto 24/7:* equivale a TP1/TP2 de los planes (ya existe en el bróker simulado)
- ✔ ⇄ **No aumentar el tamaño tras una racha ganadora** · gestión del riesgo · p. 446 · `murphy_size_after_streaks`  
  La curva de capital tiene picos y valles como un gráfico de precios. El peor momento para aumentar el tamaño es justo después de una racha ganadora (como comprar en sobrecompra); lo más prudente, aunque contraintuitivo, es empezar a aumentarlo tras un retroceso del capital.  
  *Cripto 24/7:* aplicable a los perfiles del bróker simulado  
  *Contradice:* `steenbarger_coach_risk_follows_performance`
- ✔ **Ruptura: anticipar, entrar o esperar el retroceso** · regla · p. 447, 448 · `murphy_breakout_tactics`  
  Ante una ruptura hay tres opciones: entrar anticipándola (mejor precio, más fallos), en la ruptura (más acierto, peor precio) o en el retroceso posterior (compromiso, pero los mercados más fuertes a menudo no dan segunda oportunidad). Con varias unidades se puede tomar una parte en cada momento.  
  *Cripto 24/7:* aplicable; el bróker simulado mide el llenado de las órdenes límite
- ✔ **Piramidar: solo a favor y cada vez menos** · gestión del riesgo · p. 455 · `murphy_pyramiding`  
  Al añadir posiciones, cada capa debe ser menor que la anterior, solo se añade a posiciones ganadoras, nunca a perdedoras, y el stop se lleva al punto de equilibrio. Tampoco hay que cubrir una llamada de margen: no se pone dinero bueno tras el malo.  
  *Cripto 24/7:* aplicable con apalancamiento controlado por el motor de riesgo
- · ✎ **Resumen de pautas de operación** · principio · p. 455, 456 · `murphy_trading_guidelines`  
  Resumen del autor: operar a favor de la tendencia intermedia, comprar retrocesos en alza y vender rebotes en baja, dejar correr ganancias y cortar pérdidas, usar stops, tener un plan y seguirlo, cerrar primero las perdedoras, decidir con el mercado cerrado, ir de lo largo a lo corto, sentirse cómodo en minoría y mantenerlo simple.  
  *Cripto 24/7:* «decidir con el mercado cerrado» no existe en 24/7; equivale a decidir fuera de la vela en curso

## Mark Douglas — *Trading in the Zone* (2000) · `douglas_zone` · 8 fichas

- · **Las cinco verdades del pensamiento probabilístico** · psicología · p. 92; p. 97, 98 · `douglas_zone_five_truths`  
  Douglas propone cinco verdades: puede pasar cualquier cosa; no hace falta saber qué pasará para ganar; para un conjunto de variables que definen una ventaja, ganancias y pérdidas se distribuyen al azar; una ventaja es solo una probabilidad mayor de un resultado que de otro; y cada momento del mercado es único.  
  *Cripto 24/7:* aplica al diseño de las estrategias (salidas probabilísticas, nunca certezas)
- · **La ventaja se ve en la serie, no en la operación** · principio · p. 80; p. 93 · `douglas_zone_probabilistic_edge`  
  Como un casino con su ventaja en el blackjack, el operador debe pensar en dos niveles: cada operación es incierta e independiente de las demás, pero una serie suficientemente grande con ventaja da un resultado relativamente predecible. Juzgar una ventaja por la última operación es un error; cada pérdida acerca a la siguiente ganancia si la ventaja es real.  
  *Cripto 24/7:* coincide con la evaluación por muestras de la puerta T49
- · **Definir el riesgo antes de entrar y salir sin dudar** · gestión del riesgo · p. 94; p. 130 · `douglas_zone_predefine_risk`  
  Antes de entrar hay que saber cuánto se dejará ir el mercado en contra: existe un punto en que las probabilidades de éxito ya no compensan. Si se alcanza, se sale sin dudar ni conflicto; las pérdidas son el costo del negocio para estar disponible para las ganadoras. Predefinir el riesgo es uno de los siete principios de consistencia.  
  *Cripto 24/7:* el motor de riesgo ya exige stop en cada plan; la regla vigila que no se mueva en contra
- · **Los siete principios de consistencia** · principio · p. 130 · `douglas_zone_seven_principles`  
  Ser consistente exige: identificar objetivamente las ventajas, predefinir el riesgo de cada operación, aceptarlo por completo o soltar la operación, actuar sobre la ventaja sin reservas ni dudas, cobrarse cuando el mercado ofrece ganancias, vigilar continuamente la propensión a errores y no violar nunca estos principios.  
  *Cripto 24/7:* en un sistema automático equivalen a ejecutar cada señal validada, con stop y toma de beneficio sistemática
- · **Errores típicos que nacen del miedo** · psicología · p. 22; p. 131 · `douglas_zone_trading_errors`  
  Douglas atribuye casi todos los errores a cuatro miedos (equivocarse, perder, quedarse fuera, dejar dinero en la mesa): entrar antes de la señal o muy tarde, no cortar una pérdida, salir antes de tiempo de una ganadora, no tomar beneficio y dejar que se vuelva perdedora, acercar el stop a la entrada y operar un tamaño excesivo.  
  *Cripto 24/7:* para el operador humano; en el sistema, la bitácora del bróker simulado puede contar estos desvíos
- ✔ **Ejercicio de 20 operaciones sin desviarse** · regla · p. 137, 138, 139 · `douglas_zone_twenty_trade_sample`  
  Para evaluar una ventaja, el autor pide operar al menos las 20 siguientes apariciones exactamente como está definida, sin elegir cuáles tomar ni cambiar variables, con un tamaño tal que perder las 20 sea aceptable (o en un bróker simulado). La muestra debe ser lo bastante grande para probar y lo bastante pequeña para detectar que la ventaja se degrada.  
  *Cripto 24/7:* 20 es un mínimo práctico del autor; la puerta T49 exige más muestra y fuera de muestra
- · **Primero la etapa mecánica** · principio · p. 121 · `douglas_zone_mechanical_stage`  
  Douglas describe tres etapas: mecánica (ejecutar un sistema sin fallos, pensar en probabilidades y construir confianza en la propia consistencia), subjetiva (usar todo lo aprendido vigilando los propios errores) e intuitiva. Saltarse la mecánica impide pasar a las siguientes.  
  *Cripto 24/7:* el sistema EIM opera siempre en «etapa mecánica» (reglas deterministas)
- ✔ **Tomar beneficios de forma sistemática** · gestión del riesgo · p. 92, 93, 94; p. 130 · `douglas_zone_pay_yourself`  
  Dejar que una ganadora se convierta en perdedora o no tener una forma sistemática de tomar beneficios delata la creencia de que el mercado seguirá a favor indefinidamente. El autor sabe de antemano, en la mayoría de los casos, dónde tomará beneficios; «cobrarse cuando el mercado da dinero» es uno de sus principios.  
  *Cripto 24/7:* equivale a TP1/TP2 y break-even de los perfiles del bróker simulado

## Mark Douglas — *The Disciplined Trader* (1990) · `douglas_disciplined` · 8 fichas

- · **Mercado sin estructura: hacen falta reglas propias** · principio · p. 44; p. 49 · `douglas_disciplined_unstructured_market`  
  El mercado es un entorno sin estructura, como un río que fluye sin principio ni fin: la operación empieza cuando uno entra y termina solo cuando uno sale. En un entorno así, ilimitado, es imprescindible establecer reglas que guíen la conducta y asumir toda la responsabilidad por los resultados.  
  *Cripto 24/7:* más marcado en BTC 24/7 (ni siquiera hay cierre de sesión)
- · **Diez errores típicos del operador** · psicología · p. 27 · `douglas_disciplined_typical_errors`  
  Lista del autor: negarse a definir una pérdida, no liquidar una perdedora aunque ya se sabe que su potencial cayó, aferrarse a una opinión sobre la dirección, mirar el dinero en lugar del comportamiento del mercado, operar por venganza, no girarse ante un cambio claro, no seguir las reglas del sistema, paralizarse ante la señal y devolver en una o dos operaciones lo ganado en meses.  
  *Cripto 24/7:* para el operador humano; parte se puede vigilar en la bitácora del bróker simulado
- ✔ **La venganza tras perder más de lo previsto** · psicología · p. 47, 48 · `douglas_disciplined_revenge`  
  Si una operación pierde más de lo que se pensaba arriesgar y no se asume, el operador intenta «recuperarlo»: tras perder 20 ticks, un beneficio de 10 ya no le parece suficiente aunque el mercado indique que es todo lo que queda. Eso lo pone en contra del mercado y de sí mismo y le hace ignorar la información disponible.  
  *Cripto 24/7:* regla de conducta aplicable a los perfiles del bróker simulado
- ✔ **Reglas 1 y 2: predefinir la pérdida y ejecutarla de inmediato** · gestión del riesgo · p. 170, 171 · `douglas_disciplined_loss_rules`  
  Regla 1: predefinir en cada operación qué tiene que hacer el mercado para indicar que ya no es una oportunidad en el marco operado. Regla 2: ejecutar la operación perdedora en cuanto se percibe que lo es. Así no queda nada que sopesar ni con qué tentarse, y uno queda disponible para la siguiente oportunidad, aunque sea en la misma dirección.  
  *Cripto 24/7:* en el sistema, la invalidación del escenario (T17) y el stop del plan cumplen esta función
- · **Seguir las reglas importa más que ganar** · principio · p. 167, 168 · `douglas_disciplined_rules_over_money`  
  Para el autor es más importante saber que siempre se seguirán las reglas que ganar dinero, porque lo que se gane sin esa disciplina se devolverá al mercado. Las reglas son transitorias: cambian a medida que se aprende, pero mientras rigen se cumplen.  
  *Cripto 24/7:* coherente con versionar las estrategias (T49): cambiar una regla es una versión nueva
- · **Ser experto en un solo patrón de comportamiento** · regla · p. 172 · `douglas_disciplined_one_pattern`  
  Al empezar, más información no es mejor: genera confusión y pérdidas. El autor aconseja elegir un sistema simple, preferiblemente mecánico, que identifique un patrón que se repita con cierta frecuencia, entenderlo por completo y dejar pasar las demás oportunidades hasta dominarlo.  
  *Cripto 24/7:* argumento para que T53/T54 empiecen con pocas fichas codificadas
- · **No hay oportunidades perdidas** · psicología · p. 169 · `douglas_disciplined_missed_opportunities`  
  Creer en las oportunidades perdidas causa, según el autor, casi tanto daño como no aceptar una pérdida: empuja a forzar la siguiente operación. Como el precio está en movimiento perpetuo, siempre habrá otra oportunidad; perseguir la que se fue no es necesario.  
  *Cripto 24/7:* aplicable; en el bróker simulado una orden límite no llenada simplemente caduca
- · **Operar solo dinero que se puede perder** · gestión del riesgo · p. 44; p. 170 · `douglas_disciplined_tuition_capital`  
  Solo hay que operar dinero que uno puede permitirse perder: cuanto menos significado tenga ese dinero, menos contaminan la lectura del mercado las propias preguntas de «cuánto es suficiente». El autor sugiere reservar un capital como matrícula de aprendizaje.  
  *Cripto 24/7:* coherente con «sin dinero real hasta pasar la puerta de edge y el paper trading» (CLAUDE.md)

## Brett N. Steenbarger — *The Daily Trading Coach* (2009) · `steenbarger_coach` · 11 fichas

- · **Metas de proceso y boletín diario** · psicología · p. 39 · `steenbarger_coach_process_goals`  
  Cada sesión debe tener una meta concreta sobre un proceso que uno controla (no un objetivo de ganancias), acciones para lograrla y una autoevaluación al cierre a modo de boletín de notas. Si la nota es mala, mejorar eso pasa a ser la meta del día siguiente; nunca operar sin trabajar en algún aspecto.  
  *Cripto 24/7:* en 24/7 la «sesión» es un bloque fijo (p. ej. día UTC); útil para el ciclo de mejora T51
- · **Juzgar el trading por el proceso, no por el resultado** · principio · p. 132 · `steenbarger_coach_process_over_outcome`  
  Se puede operar bien (tomar setups con ventaja demostrada, dimensionar y gestionar el riesgo) aunque la operación salga mal: incluso una ventaja de 60/40 por operación garantiza rachas de pérdidas. Definir el buen y el mal trading por el proceso, y no solo por la ganancia del día, permite ver las fortalezas en plena racha mala.  
  *Cripto 24/7:* la retroalimentación del bróker simulado separa causa del resultado (T48) en ese sentido
- ✔ **«Presionar»: forzar operaciones tras la frustración** · psicología · p. 65, 66 · `steenbarger_coach_pressing`  
  Presionar es forzar operaciones para ganar: operar demasiado grande o demasiado a menudo, intentando que pasen cosas en lugar de esperar a que el mercado ofrezca la oportunidad. Suele aparecer tras pérdidas, oportunidades perdidas o una curva plana; el antídoto son reglas de tamaño, stop, entrada y tendencia convertidas en hábito.  
  *Cripto 24/7:* medible en la bitácora del bróker simulado (frecuencia y tamaño tras pérdidas)
- ✔ **Consistencia por reglas (y la de 2:1)** · regla · p. 138, 139 · `steenbarger_coach_rule_governed`  
  Las reglas son el puente entre conductas nuevas y hábitos; el operador inconsistente suele ser el de reglas más laxas. Ejemplo del autor: no entrar sin medir antes el stop y el objetivo y tener una relación beneficio/riesgo de 2:1 o mejor, lo que frena entrar tarde en un movimiento. Los criterios de setup deben ser reglas firmes.  
  *Cripto 24/7:* la relación debe medirse neta de costos del perpetuo
- ✔ **Llevar el marcador y compararse con la propia norma** · regla · p. 256, 257, 258 · `steenbarger_coach_track_results`  
  Métricas esenciales: curva de capital, número de ganadoras y perdedoras, tamaño medio de unas y otras, resultado medio por operación y variabilidad de los retornos diarios. Lo útil es compararlas con la propia historia: si los resultados caen claramente por debajo de lo normal, reducir el tamaño y diagnosticar; no reaccionar a cada oscilación, porque mucho es azar.  
  *Cripto 24/7:* encaja con el seguimiento de sugerencias y el ciclo de mejora (T51)
- ✔ **Ventajas pequeñas suman; el tamaño decide el drawdown** · gestión del riesgo · p. 268, 269 · `steenbarger_coach_small_edge`  
  En una simulación del autor, 52 % de acierto con ganancias 1,10 veces las pérdidas dio en torno a +3 % en 100 días, y 48 % con 0,90, −3 %: poca distancia separa una ventaja positiva de una negativa. Triplicar el tamaño con esa ventaja eleva el drawdown a ~12 % y multiplicarlo por diez, a más del 40 %.  
  *Cripto 24/7:* el razonamiento es general; las cifras son de su simulación, no de BTC
- ✔ ⇄ **Arriesgar más cuando se fluye y menos cuando se decae** · gestión del riesgo · p. 313 · `steenbarger_coach_risk_follows_performance`  
  Un operador entrevistado puntúa su disciplina de entrada y salida y exige el 90 % de los puntos: entre 85 y 90 % busca causas y corrige, bajo 85 % deja de operar; también mide qué parte del movimiento posible captura (~65 %). Cuando su ejecución fluye es más agresivo; cuando decae, recorta el riesgo.  
  *Cripto 24/7:* MFE/MAE ya se registran en el bróker simulado (T47)  
  *Contradice:* `murphy_size_after_streaks`
- ✔ **Bitácora indexada y «calor» de las operaciones** · regla · p. 302; p. 324 · `steenbarger_coach_journal_metrics`  
  Indexar la bitácora por estrategia, mercado, condición, hora del día y tamaño para consultar resultados por situación. Comparar ganadoras y perdedoras por separado: cuánta pérdida flotante («calor») soportan y cuánto tardan en llegar al máximo; con eso se fijan reglas de cuándo y dónde cortar las perdedoras.  
  *Cripto 24/7:* directamente aplicable con los datos de MFE/MAE del bróker simulado
- · **Los patrones históricos son hipótesis, no conclusiones** · advertencia · p. 328, 329, 330 · `steenbarger_coach_patterns_are_hypotheses`  
  Una pauta del pasado sirve para formular hipótesis que se comprueban operando, no para operar a ciegas: los patrones dependen del periodo estudiado. Si se generan muchas hipótesis, algunas parecerán buenas por azar; deben tener sentido y ser simples. Cita a Aronson: de más de 6.000 indicadores técnicos probados, ninguno predijo con significancia.  
  *Cripto 24/7:* motivo de que toda ficha pase por la puerta T49 (Holm sobre todos los intentos)
- ✔ ⇄ **«La tendencia es tu amiga», puesta en duda** · advertencia · p. 138, 139; p. 328 · `steenbarger_coach_trend_not_friend`  
  Según la investigación del autor en el S&P 500, los retornos tras días, semanas y meses alcistas fueron peores que tras los bajistas, y comprar tras periodos alcistas rindió por debajo del mercado: la estrategia obvia falla por obvia. Desde 1980, estar por encima o por debajo de la media de 200 sesiones apenas cambió el retorno siguiente (8,68 % frente a 7,32 %).  
  *Cripto 24/7:* BTC puede comportarse distinto (la literatura académica encuentra momento en cripto); es exactamente lo que hay que medir  
  *Contradice:* `murphy_dow_trend_persists`, `lefevre_line_of_least_resistance`
- · **Autopsia de las peores decisiones** · psicología · p. 190, 191 · `steenbarger_coach_worst_trades`  
  Las peores decisiones no son necesariamente las mayores pérdidas: se reconocen por la reacción «¿cómo pude hacer eso?». Conviene revisarlas reconstruyendo qué se pensaba y sentía en ese momento para identificar el patrón (por ejemplo, no querer perder ganancias en papel o buscar el golpe de suerte) que tomó el control.  
  *Cripto 24/7:* análogo sistemático: revisar las operaciones de peor causa en la bitácora (T48)

## Jack D. Schwager — *Market Wizards (edición en español)* (1989) · `schwager_wizards_es` · 10 fichas

- · **Cortar pérdidas y dejar correr las ganancias** · gestión del riesgo · p. 36; p. 119, 120 · `schwager_wizards_es_cut_losses`  
  Es la regla más repetida por los entrevistados: Marcus la llama quizá la más importante (mantener las ganadoras y cortar las perdedoras, ambas por igual); Seykota resume los elementos del buen trading como cortar pérdidas tres veces, y sus reglas son cortar pérdidas, dejar correr las ganancias y mantener apuestas pequeñas.  
  *Cripto 24/7:* principio general; ya incorporado en el stop obligatorio de los planes
- ✔ **El stop va donde la idea queda invalidada** · gestión del riesgo · p. 65 · `schwager_wizards_es_stop_where_wrong`  
  Kovner decide el punto de salida antes de entrar y evalúa el riesgo de toda la cartera, sobre todo con posiciones correlacionadas. Moraleja de Schwager: poner el stop donde, si se alcanza, indique razonablemente que la operación está mal, no donde marque la pérdida máxima por contrato; si eso implica mucha pérdida por contrato, operar menos contratos.  
  *Cripto 24/7:* aplicable; el motor de riesgo ya fija el tamaño a partir del stop
- ✔ ⇄ **No arriesgar más del 1 % por operación** · gestión del riesgo · p. 132 · `schwager_wizards_es_one_percent_risk`  
  Larry Hite (Mint): nunca arriesgar más del 1 % del capital total en una operación, para ser indiferente a cada una; mantener el riesgo pequeño y constante y ajustar el tamaño si cambia el capital. Distingue apuestas buenas, malas, ganadoras y perdedoras: una apuesta 50/50 que paga 2 por 1 es buena aunque se pierda.  
  *Cripto 24/7:* más estricto que el 5 % de Murphy; el motor de riesgo vigente fija su propio límite  
  *Contradice:* `murphy_position_limits`
- ✔ ⇄ **Ante una racha perdedora: reducir o parar** · gestión del riesgo · p. 70; p. 80; p. 119, 120; p. 165 · `schwager_wizards_es_losing_streaks`  
  Varios entrevistados coinciden en reducir o parar ante una racha perdedora. Seykota baja la actividad y llama letal a «ponerse al día», y es más agresivo tras ganar y menos tras perder. Dennis reduce o para en las rachas y aprendió a dejar tiempo tras una pérdida que desestabiliza y a no doblar para recuperar; O'Neil revisa todo tras 5 o 6 pérdidas seguidas.  
  *Cripto 24/7:* comparable con la pausa por expectativa negativa de los perfiles (T48b)  
  *Contradice:* `murphy_size_after_streaks`
- ✔ **Sistemas que operan demasiado: los costos mandan** · advertencia · p. 106; p. 118 · `schwager_wizards_es_overtrading_costs`  
  Bielfeldt revisó sistemas vendidos al público y vio que operaban demasiado: con tanta frecuencia los costos de transacción hunden la probabilidad de que funcionen, y un sistema de tendencia viable debe ser de medio a largo plazo. Seykota añade que la rentabilidad de los sistemas de tendencia va por ciclos: su éxito atrae usuarios y, cuando el mercado se vuelve lateral, dejan de ganar.  
  *Cripto 24/7:* muy relevante: en el bróker simulado los costos explicaron ≥ 84 % de la pérdida (T47)
- ✔ **Prioridades de Seykota: tendencia, patrón, punto de entrada** · regla · p. 118 · `schwager_wizards_es_seykota_priorities`  
  Seykota ordena su trading así: primero la tendencia de largo plazo, luego el patrón gráfico actual y después un buen punto para comprar o vender; lo fundamental queda muy lejos. Sus compras se activan con un stop por encima del mercado, donde espera impulso a favor; no intenta acertar suelos ni techos.  
  *Cripto 24/7:* aplicable en 4 h/1 h con entrada por ruptura
- ✔ **Volumen que se seca en la base y crece en la ruptura** · regla · p. 178 · `schwager_wizards_es_volume_in_bases`  
  David Ryan: cuando un valor que sube consolida, el volumen debe secarse; cuando vuelve a crecer suele estar listo para arrancar. Un volumen muy alto sostenido en la consolidación hace pensar en techo. Si tras la compra el precio vuelve a caer dentro de la base, vender al menos la mitad: suele ir al extremo inferior.  
  *Cripto 24/7:* trasladable a BTC con el volumen del perpetuo
- · **Las operaciones impulsivas son las que más fallan** · psicología · p. 65 · `schwager_wizards_es_no_impulsive_trades`  
  La peor operación de Kovner nació de una decisión impulsiva; Schwager afirma, por su experiencia, que probablemente no haya clase de operaciones con más fracasos que las impulsivas (no confundir con las intuitivas). Elegida una estrategia, hay que ceñirse al plan.  
  *Cripto 24/7:* en el sistema, solo publican sugerencias las estrategias validadas (T50)
- ✔ **Flexibilidad: cambiar de opinión con la evidencia** · principio · p. 89 · `schwager_wizards_es_flexibility`  
  Paul Tudor Jones pasó de muy bajista a alcista en dos semanas porque el mercado no siguió la caída en el precio y el tiempo que esperaba: abandonó su posición y se unió al otro lado. Schwager destaca esa flexibilidad extrema como base de su éxito.  
  *Cripto 24/7:* equivale a la salida por tiempo de los planes del bróker simulado
- · **Diario con gráfico y razones de cada operación** · psicología · p. 180, 181 · `schwager_wizards_es_journal`  
  David Ryan guarda un diario: en cada compra anota en el gráfico sus razones y, al cerrar o ampliar, añade un gráfico nuevo con comentarios. Su consejo principal para el novato es aprender de los errores; su peor periodo llegó al romper su propia regla de no comprar acciones sobreextendidas.  
  *Cripto 24/7:* la bitácora del bróker simulado ya guarda razón y contexto por operación

## Edwin Lefèvre — *Reminiscences of a Stock Operator* (1923) · `lefevre_reminiscences` · 7 fichas

- ✔ ✎ **El dinero grande está en quedarse quieto** · principio · p. 55 · `lefevre_sitting_tight`  
  El narrador aprende del viejo Partridge que el dinero grande no está en las fluctuaciones individuales sino en los movimientos principales: evaluar todo el mercado y su tendencia. Acertar es fácil; lo raro es acertar y mantenerse en la posición con paciencia, y eso fue lo que le hizo ganar, no su forma de pensar.  
  *Cripto 24/7:* en BTC la «tendencia principal» de 4 h/diario; la regla choca con salidas por tiempo cortas
- ✔ **No ampliar hasta que la primera compra gane** · gestión del riesgo · p. 72, 73 · `lefevre_pyramid_on_profits`  
  No comprar toda la posición de una vez: tras la primera operación, no hacer una segunda salvo que la primera muestre ganancia; si la primera pierde, uno está equivocado, al menos por ahora, y no tiene sentido comprar más. Tampoco aconseja piramidar sin fin, sino entrar por partes con el mercado confirmando.  
  *Cripto 24/7:* aplicable con el límite de exposición del motor de riesgo
- ✔ **Nunca demasiado alto para comprar ni demasiado bajo para vender** · regla · p. 72, 73; p. 103 · `lefevre_never_too_high`  
  El narrador nunca compra porque algo parezca barato: las acciones nunca están demasiado altas para empezar a comprar ni demasiado bajas para empezar a vender. El precio por sí mismo no dice nada; lo que manda es la dirección de la menor resistencia.  
  *Cripto 24/7:* se prueba como entrada por ruptura frente a entrada por reversión
- ✔ ⇄ **Operar en la línea de menor resistencia** · regla · p. 102, 103 · `lefevre_line_of_least_resistance`  
  El especulador debe esperar a que la línea de menor resistencia se defina, cuando el precio rompe la barrera de un rango porque compras o ventas pasan a dominar, y entonces operar en esa dirección. Quienes quedaron del lado equivocado empujan el precio al cerrar; las noticias suelen confirmar una tendencia que ya existía.  
  *Cripto 24/7:* equivale a una ruptura de rango; aplicable en 1 h/4 h  
  *Contradice:* `steenbarger_coach_trend_not_friend`
- ✔ **Alcista en mercado alcista, bajista en bajista** · principio · p. 74, 75 · `lefevre_bull_in_bull_market`  
  Lo primero es determinar qué tipo de mercado se opera: todo el conjunto se mueve con la corriente principal, así que hay que ser alcista en mercado alcista y bajista en bajista. El dinero grande está en el gran movimiento, cuya continuidad depende de las condiciones de fondo, no de las manipulaciones.  
  *Cripto 24/7:* aplicable a BTC con la tendencia de 4 h/diario
- · **Esperanza y miedo, invertidos** · psicología · p. 109; p. 246 · `lefevre_hope_and_fear`  
  Los enemigos del especulador están dentro: con el mercado en contra, la esperanza le hace perder más de la cuenta; a favor, el miedo le hace salir demasiado pronto. Hay que invertir los impulsos: temer que la pérdida crezca y esperar que la ganancia se haga grande. Más adelante enumera ignorancia, codicia, miedo y esperanza.  
  *Cripto 24/7:* aplica al operador humano; el sistema lo resuelve con stop y objetivos fijados de antemano
- · **Desconfiar de soplos y opiniones; no discutir con la cinta** · advertencia · p. 74; p. 246 · `lefevre_tips_and_tape`  
  El narrador se vuelve independiente de soplos y opiniones ajenas y no discute con la cinta: enfadarse con el mercado porque va en contra es inútil. Avisa de que la desinformación deliberada, como las noticias alcistas difundidas para colocar papel, es más insidiosa que los soplos corrientes.  
  *Cripto 24/7:* refuerza que el agente de contexto (LLM) solo informa y nunca abre operaciones

## Cruces entre autores (contradicciones)

- ✔ **¿Subir o bajar el tamaño tras un retroceso del capital?** · advertencia · murphy p. 446; schwager p. 119, 120; steenbarger p. 258 · `cruce_size_after_drawdown`  
  Los autores se contradicen. Murphy: no aumentar el tamaño tras una racha ganadora y empezar a aumentarlo tras un retroceso del capital. Seykota y otros entrevistados de Schwager: reducir o parar en las rachas perdedoras y ser más agresivo tras ganar. Steenbarger: recortar el riesgo cuando los resultados caen bajo la propia norma. Es una hipótesis a medir, no una regla.  
  *Cripto 24/7:* se compara en los perfiles del bróker simulado, fuera de muestra (T54)
- ✔ **¿Seguir la tendencia o ir contra el movimiento reciente?** · advertencia · murphy p. 65; lefevre p. 102; nison p. 43; steenbarger p. 328 · `cruce_trend_vs_reversal`  
  Murphy (Dow), Lefèvre y Nison sostienen que la tendencia vigente tiende a continuar y que hay que operar a su favor. Steenbarger documenta en el S&P 500 lo contrario en horizontes de días a meses: peores retornos tras periodos alcistas y la estrategia obvia fallando. Para BTC hay que medirlo por marco y horizonte antes de dar peso a cualquiera de las dos lecturas.  
  *Cripto 24/7:* el resultado puede depender del marco; el agente `literature` (T53) debe mostrar ambas fichas cuando apliquen
- · **Riesgo por operación: del 1 % al 5 %** · advertencia · murphy p. 443; schwager p. 120; schwager p. 132 · `cruce_risk_per_trade`  
  Las cifras de riesgo máximo por operación varían entre autores: Murphy da hasta un 5 % del capital como pauta estándar en futuros, Seykota dice arriesgar por debajo del 5 % y Larry Hite fija el 1 %. Ninguna está pensada para perpetuos cripto apalancados 24/7; el límite lo fija el motor de riesgo del sistema, no estas fichas.  
  *Cripto 24/7:* solo informa; el riesgo vigente (risk_v2) manda y es determinista
